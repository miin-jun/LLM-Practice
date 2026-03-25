import os
import base64
import html
from pathlib import Path
from datetime import datetime
import folium
from streamlit_folium import st_folium
import pandas as pd
import streamlit as st
from dotenv import dotenv_values

# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(
    page_title="간첩판독기",
    page_icon="🕵️",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def resolve_existing_path(candidates):
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


PROV_CSV = resolve_existing_path([
    BASE_DIR / "data" / "north_korea_events_전처리.csv",
    BASE_DIR / "north_korea_events_전처리.csv",
])

SHELTER_CSV = resolve_existing_path([
    BASE_DIR / "data" / "민방위대피시설_전처리.csv",
    BASE_DIR / "민방위대피시설_전처리.csv",
])

# 배경 이미지 경로 (data/ 폴더 또는 루트에 위치)
BAD_IMG_PATH = resolve_existing_path([
    BASE_DIR / "data" / "표돌이.jpeg",
    BASE_DIR / "표돌이.jpeg",
])
GOOD_IMG_PATH = resolve_existing_path([
    BASE_DIR / "data" / "안심.jpeg",
    BASE_DIR / "안심.jpeg",
])

# =========================================================
# 이미지 → base64 변환
# =========================================================
def img_to_base64(path: Path) -> str:
    if path.exists():
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

BAD_IMG_B64  = img_to_base64(BAD_IMG_PATH)
GOOD_IMG_B64 = img_to_base64(GOOD_IMG_PATH)

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
KAKAO_JS_KEY   = get_env_value("KAKAO_JS_KEY")

if OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# =========================================================
# 세션 초기화
# =========================================================
defaults = {
    "messages":              [],
    "api_messages":          [],
    "chain":                 None,
    "rag_ready":             False,
    "rag_error":             "",
    "question_count":        0,
    "shelter_df":            None,
    "shelter_error":         "",
    "security_bad_count":    0,    # 안보 의식 없음 누적
    "security_good_count":   0,    # 안보 의식 있음 누적
    "last_judgment":         "none",  # "bad" | "good" | "none"
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================================================
# CSS (카카오톡 스타일)
# =========================================================
st.markdown("""
<style>
.stApp {
    background-color: #97B89A;
    background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%2382a885' fill-opacity='0.35'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
}
.chat-header {
    background-color: #2C2C54;
    color: white;
    padding: 14px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
    font-size: 17px;
    font-weight: 600;
    margin-bottom: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    position: relative;
    z-index: 10;
}
.date-divider-wrapper {
    display: flex;
    justify-content: center;
    margin: 6px 0;
    position: relative;
    z-index: 10;
}
.date-divider {
    color: white;
    font-size: 12px;
    background-color: rgba(0,0,0,0.2);
    border-radius: 12px;
    padding: 3px 12px;
}
.security-badge {
    display: flex;
    gap: 12px;
    justify-content: center;
    margin: 6px 0;
    position: relative;
    z-index: 10;
}
.badge-bad {
    background-color: rgba(180,30,30,0.8);
    color: white;
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: bold;
}
.badge-good {
    background-color: rgba(30,120,60,0.8);
    color: white;
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: bold;
}
.msg-row-ai {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    justify-content: flex-start;
    position: relative;
    z-index: 10;
    margin-bottom: 4px;
}
.ai-avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: linear-gradient(135deg, #2C2C54, #706fd3);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2);
}
.ai-name {
    font-size: 12px;
    color: white;
    margin-bottom: 4px;
    font-weight: 500;
}
.bubble-ai {
    background-color: #ffffff;
    border-radius: 0px 16px 16px 16px;
    padding: 10px 14px;
    max-width: 72%;
    font-size: 14px;
    font-weight: bold;
    line-height: 1.6;
    color: #1a1a1a;
    box-shadow: 0 1px 4px rgba(0,0,0,0.12);
    word-break: keep-all;
}
.msg-time-ai {
    font-size: 11px;
    color: rgba(255,255,255,0.8);
    align-self: flex-end;
    margin-left: 4px;
    white-space: nowrap;
}
.msg-row-user {
    display: flex;
    align-items: flex-end;
    gap: 6px;
    justify-content: flex-end;
    position: relative;
    z-index: 10;
    margin-bottom: 4px;
}
.bubble-user {
    background-color: #FFEB01;
    border-radius: 16px 0px 16px 16px;
    padding: 10px 14px;
    max-width: 72%;
    font-size: 14px;
    line-height: 1.6;
    color: #1a1a1a;
    box-shadow: 0 1px 4px rgba(0,0,0,0.12);
    word-break: keep-all;
}
.msg-time-user {
    font-size: 11px;
    color: rgba(255,255,255,0.8);
    align-self: flex-end;
    white-space: nowrap;
}
#MainMenu {visibility: hidden;}
footer    {visibility: hidden;}
header    {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# =========================================================
# 배경 오버레이 렌더링
# =========================================================
def render_background():
    bad_count  = st.session_state.security_bad_count
    good_count = st.session_state.security_good_count
    last       = st.session_state.last_judgment

    if last == "bad" and bad_count > 0 and BAD_IMG_B64:
        opacity = round(min(bad_count / 3, 1.0), 2)
        img_b64 = BAD_IMG_B64
    elif last == "good" and good_count > 0 and GOOD_IMG_B64:
        opacity = round(min(good_count / 3, 1.0), 2)
        img_b64 = GOOD_IMG_B64
    else:
        return  # 오버레이 없음

    st.markdown(f"""
    <div style="
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background-image: url('data:image/jpeg;base64,{img_b64}');
        background-size: cover;
        background-position: center;
        opacity: {opacity};
        z-index: 0;
        pointer-events: none;
    "></div>
    """, unsafe_allow_html=True)


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


def now_time() -> str:
    return datetime.now().strftime("%p %I:%M").replace("AM", "오전").replace("PM", "오후")


def render_bubble(role: str, content: str, time_str: str):
    content_html = html.escape(content).replace("\n", "<br>")
    if role == "assistant":
        st.markdown(f"""
        <div class="msg-row-ai">
            <div class="ai-avatar">🕵️</div>
            <div>
                <div class="ai-name">간첩판독기</div>
                <div class="bubble-ai">{content_html}</div>
            </div>
            <div class="msg-time-ai">{time_str}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="msg-row-user">
            <div class="msg-time-user">{time_str}</div>
            <div class="bubble-user">{content_html}</div>
        </div>
        """, unsafe_allow_html=True)

# =========================================================
# 안보 의식 분류 (AI 답변 말투 기준)
# =========================================================
def classify_security(ai_answer: str) -> str:
    """
    AI 답변 말투만 보고 판정
    - 비꼬거나 공격적이면 bad
    - 친절하고 칭찬/설명형이면 good
    - 애매하면 neutral
    """
    text = str(ai_answer).strip()

    if not text:
        return "neutral"

    bad_patterns = [
        "아니, 진짜로 그렇게 생각해",
        "그게 말이 돼",
        "너무 안이한 생각",
        "현실 좀 똑바로 봐라",
        "도대체 뭘 믿고",
        "안이한 생각",
        "의아",
        "비꼬",
        "핀잔",
        "정말 그렇게",
        "현실을 봐라",
    ]

    good_patterns = [
        "좋은 질문",
        "설명드리겠습니다",
        "설명해드리겠습니다",
        "알겠습니다",
        "예를 들어",
        "또한",
        "이유는",
        "직접적인 위협",
        "필수적입니다",
        "든든하네요",
        "제대로 된 안보 의식",
        "안보 개념이 뚜렷",
    ]

    bad_score = sum(1 for p in bad_patterns if p in text)
    good_score = sum(1 for p in good_patterns if p in text)

    # 말투 보정
    # if "?" in text and any(x in text for x in ["그게 말이 돼", "진짜로", "도대체"]):
    #     bad_score += 1

    # if any(x in text for x in ["네요!", "좋습니다", "설명해드릴게요", "필수적입니다", "든든하네요"]):
    #     good_score += 1

    if bad_score > good_score and bad_score > 0:
        return "bad"
    if good_score > bad_score and good_score > 0:
        return "good"
    return "neutral"

# =========================================================
# 대피소 데이터
# =========================================================
@st.cache_data(show_spinner=False)
def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def prepare_shelter_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    lat_col  = pick_first_existing(df.columns, ["위도(EPSG4326)", "위도", "LAT", "lat"])
    lon_col  = pick_first_existing(df.columns, ["경도(EPSG4326)", "경도", "LON", "lon"])
    name_col = pick_first_existing(df.columns, ["시설명", "시설위치", "대피시설명"])
    addr_col = pick_first_existing(df.columns, ["소재지전체주소", "도로명전체주소", "주소"])
    cap_col  = pick_first_existing(df.columns, ["최대수용인원", "수용인원"])

    if lat_col is None or lon_col is None:
        raise ValueError("대피소 CSV에서 위도/경도 컬럼을 찾지 못했습니다.")

    result = pd.DataFrame()
    result["lat"]      = pd.to_numeric(df[lat_col], errors="coerce")
    result["lon"]      = pd.to_numeric(df[lon_col], errors="coerce")
    result["name"]     = df[name_col].fillna("").astype(str) if name_col else [f"대피소 {i+1}" for i in range(len(df))]
    result["address"]  = df[addr_col].fillna("").astype(str) if addr_col else ""
    result["capacity"] = df[cap_col].fillna("").astype(str)  if cap_col  else ""
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
    for _, row in df.head(max_markers).iterrows():
        popup_html = (
            f"<b>{row.get('name','대피소')}</b><br>"
            f"{row.get('address','')}<br>"
            f"수용인원: {row.get('capacity','')}"
        )
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
            f"Date: {row['Date']}\nType: {row['Type']}\n"
            f"Event: {row['Event']}\nDescription: {row['Description']}"
        )
        docs.append(Document(
            page_content=content,
            metadata={"date": str(row["Date"]), "type": str(row["Type"]), "event": str(row["Event"])},
        ))

    embedding_model = OpenAIEmbeddings(model="text-embedding-3-small", api_key=openai_api_key)
    vector_store = Chroma.from_documents(
        documents=docs, embedding=embedding_model,
        collection_name="north_korea_events_streamlit",
    )
    retriever = vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 3})

    def format_docs(documents):
        if not documents:
            return "관련 과거 사례를 찾지 못했습니다."
        return "\n\n".join(doc.page_content for doc in documents)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """
당신은 북한의 과거 도발 사례를 설명하는 분석 도우미이자 전문가입니다.
사용자가 안전불감증 같아 보일 때, 안보 개념이 없어 보일 때는 비꼬는 듯한 말투로 왜 우리나라에는 전쟁이 안날거라고 생각하는지 정말
의아해하면서 답을 해줍니다.
반면에 사용자가 안보개념이 뚜렷해 보일 때는 과거 사례들을 들어가면서 친절하게 설명해줍니다.

규칙
1. 질문과 관련된 답을 할 때는 반드시 제공된 context만 근거로 답해라.
2. context 밖의 사실을 지어내지 마라.
3. 반드시 과거 사례를 포함시켜서 말해라. 사례가 없으면 없다고 말해라.
4. 답변은 한국어로 작성해라.
5. 이전 대화 맥락도 반영해라.
6. 안보 개념이 없어 보일 때는 비꼬는 듯이 말해라.
7. 안보 개념이 없어 보일 때는 비속어도 꼭 포함시켜서 말해라.
8. '씨발', '좆', '개새끼' 등의 단어는 반드시 제외해서 말해라.

이전 대화:
{chat_history}

context:
{context}
        """.strip()),
        ("human", "질문: {question}"),
    ])

    llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.2, api_key=openai_api_key)
    chain = (
        {
            "context":      itemgetter("question") | retriever | RunnableLambda(format_docs),
            "question":     itemgetter("question"),
            "chat_history": itemgetter("chat_history"),
        }
        | prompt | llm | StrOutputParser()
    )
    return chain

# =========================================================
# 초기 리소스 로드
# =========================================================
def initialize_resources():
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

# 배경 오버레이 (항상 먼저 렌더링)
render_background()

# =========================================================
# 사이드바
# =========================================================
with st.sidebar:
    st.title("🕵️ 간첩판독기")
    st.divider()

    bad  = st.session_state.security_bad_count
    good = st.session_state.security_good_count
    st.subheader("🔍 안보 의식 판독 현황")
    st.markdown(f"🚨 **위험 판정**: {bad} / 3회")
    st.progress(min(bad / 3, 1.0))
    st.markdown(f"✅ **안전 판정**: {good} / 3회")
    st.progress(min(good / 3, 1.0))

    st.divider()
    if st.button("🔄 다시 초기화", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        for k, v in defaults.items():
            st.session_state[k] = v
        st.rerun()

    if st.button("🗑️ 대화 초기화", use_container_width=True):
        st.session_state.messages              = []
        st.session_state.api_messages          = []
        st.session_state.question_count        = 0
        st.session_state.security_bad_count    = 0
        st.session_state.security_good_count   = 0
        st.session_state.last_judgment         = "none"
        st.rerun()

# =========================================================
# 메인 탭
# =========================================================
tab_chat, tab_shelter = st.tabs(["💬 간첩판독기", "🗺️ 민방위 대피소 지도"])

# =========================================================
# 탭 1: 챗봇
# =========================================================
with tab_chat:
    st.markdown("""
    <div class="chat-header">
        🕵️&nbsp;&nbsp;간첩판독기 — 당신의 안보 의식을 판독합니다
    </div>
    """, unsafe_allow_html=True)

    today = (
        datetime.now().strftime("%Y년 %m월 %d일 %A")
        .replace("Monday","월요일").replace("Tuesday","화요일")
        .replace("Wednesday","수요일").replace("Thursday","목요일")
        .replace("Friday","금요일").replace("Saturday","토요일")
        .replace("Sunday","일요일")
    )
    st.markdown(f"""
    <div class="date-divider-wrapper">
        <div class="date-divider">{today}</div>
    </div>
    """, unsafe_allow_html=True)

    # 안보 뱃지
    bad  = st.session_state.security_bad_count
    good = st.session_state.security_good_count
    if bad > 0 or good > 0:
        st.markdown(f"""
        <div class="security-badge">
            <span class="badge-bad">🚨 위험 판정 {bad}/3</span>
            <span class="badge-good">✅ 안전 판정 {good}/3</span>
        </div>
        """, unsafe_allow_html=True)

    if not st.session_state.rag_ready:
        st.warning("RAG가 아직 준비되지 않았습니다. 왼쪽 상태 메시지를 먼저 확인하세요.")
    else:
        if not st.session_state.messages:
            welcome = "안녕하세요! 저는 간첩판독기입니다 🕵️\n당신의 안보 의식을 판독하겠습니다.\n북한 관련 질문을 자유롭게 해보세요.\n안보 의식이 흐릿하다면... 각오하세요."
            st.session_state.messages.append({
                "role": "assistant", "content": welcome, "time": now_time(),
            })

        for msg in st.session_state.messages:
            render_bubble(msg["role"], msg["content"], msg["time"])

        st.markdown("<br>", unsafe_allow_html=True)

        with st.form(key="chat_form", clear_on_submit=True):
            col1, col2 = st.columns([5, 1])
            with col1:
                user_text = st.text_input(
                    label="메시지",
                    placeholder="예: 한미연합훈련은 대체 왜 하는 거야??",
                    label_visibility="collapsed",
                )
            with col2:
                send_btn = st.form_submit_button("➤")

        if send_btn and user_text.strip():
            user_input = user_text.strip()
            t = now_time()
            st.session_state.messages.append({"role": "user", "content": user_input, "time": t})

            history_text = "\n".join([
                f"{'사용자' if m['role'] == 'user' else 'AI'}: {m['content']}"
                for m in st.session_state.messages[-8:]
            ])

            with st.spinner("판독 중입니다..."):
                try:
                    answer = st.session_state.chain.invoke({
                        "question": user_input,
                        "chat_history": history_text,
                    })
                except Exception as e:
                    answer = f"답변 생성 중 오류가 발생했습니다: {e}"
                # AI 답변 말투 기준으로 판독
                judgment = classify_security(answer)

            # 카운터 업데이트
            if judgment == "bad":
                st.session_state.security_bad_count += 1
                st.session_state.last_judgment = "bad"
            elif judgment == "good":
                st.session_state.security_good_count += 1
                st.session_state.last_judgment = "good"

            st.session_state.messages.append({"role": "assistant", "content": answer, "time": now_time()})
            st.session_state.question_count += 1
            st.rerun()

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
            keyword = st.text_input("시설명/주소 검색", placeholder="예: 강남구, 종로구, 서울특별시")
        with c2:
            regions = sorted([r for r in shelter_df["region"].dropna().unique().tolist() if r])
            selected_region = st.selectbox("지역 선택", options=["전체"] + regions, index=0)

        if selected_region != "전체":
            shelter_df = shelter_df[shelter_df["region"] == selected_region].reset_index(drop=True)
        if keyword:
            shelter_df = shelter_df[
                shelter_df["name"].str.contains(keyword, case=False, na=False)
                | shelter_df["address"].str.contains(keyword, case=False, na=False)
            ].reset_index(drop=True)

        st.caption(f"현재 표시 대상: {len(shelter_df):,}개 (지도에는 최대 500개 표시)")

        if shelter_df.empty:
            st.warning("검색 결과가 없습니다.")
        else:
            m = build_folium_map(shelter_df)
            st_folium(m, width="100%", height=650)