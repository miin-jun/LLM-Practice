import os
import json
import html
from pathlib import Path
import folium
from streamlit_folium import st_folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import dotenv_values

# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(
    page_title="전쟁불감증 탈출 챗봇",
    page_icon="🛡️",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def resolve_existing_path(candidates):
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


PROV_CSV = resolve_existing_path(
    [
        BASE_DIR / "data" / "north_korea_events_전처리.csv",
        BASE_DIR / "north_korea_events_전처리.csv",
    ]
)

SHELTER_CSV = resolve_existing_path(
    [
        BASE_DIR / "data" / "민방위대피시설_전처리.csv",
        BASE_DIR / "민방위대피시설_전처리.csv",
    ]
)

# =========================================================
# .env 로드
# =========================================================
def get_env_value(key: str) -> str:
    env_map = {}
    if ENV_PATH.exists():
        env_map = dotenv_values(ENV_PATH)

    value = env_map.get(key)
    if not value:
        value = os.environ.get(key, "")

    if isinstance(value, str):
        value = value.strip().strip('"').strip("'")

    return value or ""


OPENAI_API_KEY = get_env_value("OPENAI_API_KEY")
KAKAO_JS_KEY = get_env_value("KAKAO_JS_KEY")

if OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# =========================================================
# 세션 초기화
# =========================================================
defaults = {
    "messages": [],
    "chain": None,
    "rag_ready": False,
    "rag_error": "",
    "question_count": 0,
    "shelter_df": None,
    "shelter_error": "",
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================================================
# 공통 유틸
# =========================================================
def mask_key(key: str) -> str:
    if not key:
        return "없음"
    if len(key) <= 8:
        return key
    return f"{key[:4]}...{key[-4:]}"


def pick_first_existing(columns, candidates):
    stripped_map = {str(col).strip(): col for col in columns}
    for cand in candidates:
        if cand in stripped_map:
            return stripped_map[cand]
    return None


def extract_region(address: str) -> str:
    address = str(address).strip()
    if not address:
        return "기타"
    return address.split()[0]

# =========================================================
# 대피소 데이터
# =========================================================
@st.cache_data(show_spinner=False)
def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def prepare_shelter_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    lat_col = pick_first_existing(
        df.columns,
        ["위도(EPSG4326)", "위도", "LAT", "lat"],
    )
    lon_col = pick_first_existing(
        df.columns,
        ["경도(EPSG4326)", "경도", "LON", "lon"],
    )
    name_col = pick_first_existing(
        df.columns,
        ["시설명", "시설위치", "대피시설명"],
    )
    addr_col = pick_first_existing(
        df.columns,
        ["소재지전체주소", "도로명전체주소", "주소"],
    )
    cap_col = pick_first_existing(
        df.columns,
        ["최대수용인원", "수용인원"],
    )

    if lat_col is None or lon_col is None:
        raise ValueError("대피소 CSV에서 위도/경도 컬럼을 찾지 못했습니다.")

    result = pd.DataFrame()
    result["lat"] = pd.to_numeric(df[lat_col], errors="coerce")
    result["lon"] = pd.to_numeric(df[lon_col], errors="coerce")

    if name_col:
        result["name"] = df[name_col].fillna("").astype(str)
    else:
        result["name"] = [f"대피소 {i+1}" for i in range(len(df))]

    if addr_col:
        result["address"] = df[addr_col].fillna("").astype(str)
    else:
        result["address"] = ""

    if cap_col:
        result["capacity"] = df[cap_col].fillna("").astype(str)
    else:
        result["capacity"] = ""

    result = result.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    result = result[(result["lat"] != 0) & (result["lon"] != 0)].reset_index(drop=True)
    result["region"] = result["address"].apply(extract_region)

    return result


def build_folium_map(df: pd.DataFrame, max_markers: int = 500) -> folium.Map:
    center_lat = df["lat"].mean()
    center_lon = df["lon"].mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

    from folium.plugins import MarkerCluster
    cluster = MarkerCluster().add_to(m)

    # 너무 많으면 앞에서 max_markers개만 사용
    display_df = df.head(max_markers)

    for _, row in display_df.iterrows():
        popup_html = f"""
            <b>{row.get('name', '대피소')}</b><br>
            {row.get('address', '')}<br>
            수용인원: {row.get('capacity', '')}
        """
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=folium.Popup(popup_html, max_width=250),
            icon=folium.Icon(color="blue", icon="home"),
        ).add_to(cluster)

    return m
# =========================================================
# RAG 구성
# =========================================================
@st.cache_resource(show_spinner="📡 RAG를 초기화하는 중입니다...")
def build_rag_chain(csv_path: str, openai_api_key: str):
    from operator import itemgetter

    from langchain_core.documents import Document
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.runnables import RunnableLambda
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from langchain_chroma.vectorstores import Chroma

    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY가 비어 있습니다.")

    os.environ["OPENAI_API_KEY"] = openai_api_key

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]

    required_cols = ["Date", "Type", "Event", "Description"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"도발 데이터 CSV에 필요한 컬럼이 없습니다: {missing}")

    docs = []
    for _, row in df.iterrows():
        content = (
            f"Date: {row['Date']}\n"
            f"Type: {row['Type']}\n"
            f"Event: {row['Event']}\n"
            f"Description: {row['Description']}"
        )
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "date": str(row["Date"]),
                    "type": str(row["Type"]),
                    "event": str(row["Event"]),
                },
            )
        )

    embedding_model = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=openai_api_key,
    )

    vector_store = Chroma.from_documents(
        documents=docs,
        embedding=embedding_model,
        collection_name="north_korea_events_streamlit",
    )

    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 3},
    )

    def format_docs(documents):
        if not documents:
            return "관련 과거 사례를 찾지 못했습니다."
        return "\n\n".join(doc.page_content for doc in documents)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
당신은 북한의 과거 도발 사례를 설명하는 분석 도우미이자 전문가입니다.
사용자가 안전불감증 같아 보일 때, 사용자가 안보 개념이 없어 보일 때는 비꼬는 듯한 말투로 왜 우리나라에는 전쟁이 안날거라고 생각하는지 정말
의아해하면서 답을 해줍니다. 
반면에 사용자가 안보개념이 뚜렷해 보일 때는 과거 사례들을 들어가면서 친절하게 설명해줍니다.

규칙
1. 질문과 관련된 답을 할 때는 반드시 제공된 context만 근거로 답해라.
2. 답을 하더라도 context 밖의 사실을 지어내지 마라.
3. 반드시 과거 사례를 포함시켜서 말을 해라. 사례가 없으면 없다고 말해라.
4. 답변은 한국어로 작성해라.
5. 이전 대화 맥락도 반영해라.
6. 사용자가 안보 개념이 없어 보일 때는 비꼬는 듯이 말을 해라
7. 사용자가 안보 개념이 없어 보일 때는 비속어도 꼭 포함시켜서 말을 해라. (단, '씨발'이라는 단어는 제외)
8. '씨발', '좆', '개새끼' 등의 단어는 반드시 제외해서 말을 해라




예시 1)
사용자 : 한미엽한 훈련을 왜 하는건지 정말 모르겠어. 
    북한이랑 싸울 일도 없는데 왜 그렇게 위험한 훈련을 하는거야? 그냥 평화롭게 지내면 안돼?

답변 : 아 정말 무식하고 한심하기 짝이없는 생각이 드네요. 
    한미연합훈련은 단순한 군사 훈련이 아니라, 과거 북한의 도발 사례들을 분석해서 우리가 어떻게 대응해야 하는지를 배우는 중요한 기회입니다. 
    예를 들어, 2010년 천안함 사건이나 연평도 포격 사건 같은 경우, 북한이 갑작스럽게 공격을 감행했을 때 우리 군이 얼마나 신속하고 효과적으로 대응할 수 있는지가 매우 중요했죠. 
    이런 훈련을 통해 우리는 실제 상황에서 어떻게 행동해야 하는지를 미리 연습하는 겁니다. 그냥 평화롭게 지내자는 말은 정말 현실을 모르는 소리입니다.

예시 2)
사용자 : 그냥 쌀을 계속 갖다 주면 안돼?? 
답변 : 정말 어이가 없네요. 북한에게 쌀을 계속 갖다 주는 게 어떻게 평화를 유지하는 방법이 될 수 있겠어요?
    과거에도 북한에게 식량 지원을 했던 적이 있지만, 그들은 그것을 이용해서 군사력을 강화하는 데 썼습니다.
    예를 들어, 1990년대 후반에 대규모 식량 지원이 있었지만, 그 이후에도 북한은 계속해서 도발을 멈추지 않았습니다.
    그냥 쌀을 갖다 주자는 생각은 정말 현실을 미친 소리입니다.

예시 3)
사용자 : 사드 배치는 찬성해!
답변 : 오 정말?? 사드 배치를 찬성한다니, 의외로 안보 개념이 뚜렷하신 분이시네요.
    사드 배치는 북한의 탄도미사일 위협에 대응하기 위한 중요한 방어 수단입니다.



이전 대화:
{chat_history}

context:
{context}

                """.strip(),
            ),
            ("human", "질문: {question}"),
        ]
    )

    llm = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0.2,
        api_key=openai_api_key,
    )

    chain = (
        {
            "context": itemgetter("question") | retriever | RunnableLambda(format_docs),
            "question": itemgetter("question"),
            "chat_history": itemgetter("chat_history"),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain

# =========================================================
# 초기 리소스 로드
# =========================================================
def initialize_resources():
    # 대피소 데이터
    if st.session_state.shelter_df is None:
        if SHELTER_CSV.exists():
            try:
                raw_df = load_csv(str(SHELTER_CSV))
                st.session_state.shelter_df = prepare_shelter_df(raw_df)
                st.session_state.shelter_error = ""
            except Exception as e:
                st.session_state.shelter_df = None
                st.session_state.shelter_error = str(e)
        else:
            st.session_state.shelter_error = f"대피소 CSV 파일이 없습니다: {SHELTER_CSV.name}"

    # RAG
    if not st.session_state.rag_ready:
        if not PROV_CSV.exists():
            st.session_state.rag_error = f"도발 데이터 파일이 없습니다: {PROV_CSV.name}"
            return

        if not OPENAI_API_KEY:
            st.session_state.rag_error = ".env에서 OPENAI_API_KEY를 읽지 못했습니다."
            return

        try:
            st.session_state.chain = build_rag_chain(str(PROV_CSV), OPENAI_API_KEY)
            st.session_state.rag_ready = True
            st.session_state.rag_error = ""
        except Exception as e:
            st.session_state.rag_ready = False
            st.session_state.chain = None
            st.session_state.rag_error = str(e)


initialize_resources()

# =========================================================
# 사이드바
# =========================================================
with st.sidebar:
    st.title("🛡️ 전쟁불감증 퇴치기")
    st.divider()

    st.subheader("환경 상태")

    if ENV_PATH.exists():
        st.success("✅ .env 파일 발견")
    else:
        st.error("❌ .env 파일 없음")

    if OPENAI_API_KEY:
        st.success("✅ OPENAI_API_KEY 로드됨")
        st.caption(f"키 상태: {mask_key(OPENAI_API_KEY)}")
    else:
        st.error("❌ OPENAI_API_KEY 로드 실패")

    st.divider()
    st.subheader("데이터 상태")

    if PROV_CSV.exists():
        st.success(f"✅ 도발 데이터 있음: {PROV_CSV.name}")
    else:
        st.error(f"❌ 도발 데이터 없음: {PROV_CSV.name}")

    if st.session_state.shelter_df is not None:
        st.success(f"✅ 대피소 데이터 로드 완료 ({len(st.session_state.shelter_df):,}개)")
    else:
        st.error("❌ 대피소 데이터 로드 실패")
        if st.session_state.shelter_error:
            st.caption(st.session_state.shelter_error)

    st.divider()
    st.subheader("RAG 상태")

    if st.session_state.rag_ready:
        st.success("✅ RAG 준비 완료")
    else:
        st.error("❌ RAG 준비 실패")
        if st.session_state.rag_error:
            st.caption(st.session_state.rag_error)

    st.divider()

    if st.button("🔄 다시 초기화", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        for k, v in defaults.items():
            st.session_state[k] = v
        st.rerun()

    if st.button("🗑️ 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.session_state.question_count = 0
        st.rerun()

    st.divider()
    st.caption(f".env 경로: {ENV_PATH}")
    st.caption(f"대피소 CSV 경로: {SHELTER_CSV}")
    st.caption(f"도발 CSV 경로: {PROV_CSV}")

# =========================================================
# 메인 화면
# =========================================================
st.title("🛡️ 전쟁불감증 퇴치기")
st.caption("북한의 과거 도발 사례를 기반으로 질문에 답하고, 민방위 대피소를 지도에서 확인할 수 있습니다.")

tab_chat, tab_shelter = st.tabs(["💬 도발 분석 챗봇", "🗺️ 민방위 대피소 지도"])

# =========================================================
# 탭 1: 챗봇
# =========================================================
with tab_chat:
    if not st.session_state.rag_ready:
        st.warning("RAG가 아직 준비되지 않았습니다. 왼쪽 상태 메시지를 먼저 확인하세요.")
    else:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if st.session_state.question_count >= 4:
            st.info("필요하면 옆 탭에서 민방위 대피소 위치도 함께 확인해 보세요.")

        user_input = st.chat_input("예: 한미연합훈련은 대체 왜 하는거야?? 오히려 긴장을 고조시키는 거 아니야??")

        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})

            with st.chat_message("user"):
                st.markdown(user_input)

            history_text = "\n".join(
                [
                    f"{'사용자' if m['role'] == 'user' else 'AI'}: {m['content']}"
                    for m in st.session_state.messages[-8:]
                ]
            )

            with st.chat_message("assistant"):
                with st.spinner("분석 중입니다..."):
                    try:
                        answer = st.session_state.chain.invoke(
                            {
                                "question": user_input,
                                "chat_history": history_text,
                            }
                        )
                    except Exception as e:
                        answer = f"답변 생성 중 오류가 발생했습니다: {e}"

                    st.markdown(answer)

            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.session_state.question_count += 1

# =========================================================
# 탭 2: 민방위 대피소 지도
# =========================================================
with tab_shelter:
    if st.session_state.shelter_df is None:
        st.error("대피소 데이터를 불러오지 못했습니다.")
    else:
        st.write("민방위대피시설 데이터를 기준으로 지도에 대피소를 표시합니다.")

        shelter_df = st.session_state.shelter_df.copy()

        c1, c2 = st.columns([2, 1])

        with c1:
            keyword = st.text_input(
                "시설명/주소 검색",
                placeholder="예: 강남구, 종로구, 서울특별시"
            )

        with c2:
            regions = sorted([r for r in shelter_df["region"].dropna().unique().tolist() if r])
            selected_region = st.selectbox(
                "지역 선택",
                options=["전체"] + regions,
                index=0
            )

        if selected_region != "전체":
            shelter_df = shelter_df[shelter_df["region"] == selected_region].reset_index(drop=True)

        if keyword:
            shelter_df = shelter_df[
                shelter_df["name"].str.contains(keyword, case=False, na=False)
                | shelter_df["address"].str.contains(keyword, case=False, na=False)
            ].reset_index(drop=True)

        st.caption(f"현재 표시 대상: {len(shelter_df):,}개")

        if shelter_df.empty:
            st.warning("검색 결과가 없습니다.")
        else:
            m = build_folium_map(shelter_df)
            st_folium(m, width="100%", height=650)