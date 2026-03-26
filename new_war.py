import os
import html
import random
import base64
from pathlib import Path
from datetime import datetime
import folium
from streamlit_folium import st_folium
import pandas as pd
import streamlit as st
from dotenv import dotenv_values

# =========================================================
# 고정 데이터
# =========================================================
# =========================================================
# 배경 이미지
# =========================================================
def resolve_img_path(candidates):
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]

def img_to_base64(path) -> str:
    if path.exists():
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

NAMES = [
    "박세현", "박수영", "김수진", "권민제", "김지원",
    "김은우", "정재훈", "권민세", "최하진", "김규호",
    "김현수", "진세형",
    "정석원", "임정희", "조아름",
    "황인규", "박영훈", "김유진",
    "최현진", "강사님",
]

QUESTIONS = [
    "사드(THAAD) 배치에 대해서 어떻게 생각하시나요?",
    "한미 동맹에 대해서 어떻게 생각하시나요?",
    "김정은에 대해 한마디 해보세요.",
]

# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(page_title="나락퀴즈쇼", page_icon="🕵️", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH  = BASE_DIR / ".env"

def resolve_existing_path(candidates):
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]

PROV_CSV = resolve_existing_path([
    BASE_DIR / "data" / "north_korea_events_전처리.csv",
    BASE_DIR / "north_korea_events_전처리.csv",
])
SHELTER_CSV = resolve_existing_path([
    BASE_DIR / "data" / "민방위대피시설_전처리.csv",
    BASE_DIR / "민방위대피시설_전처리.csv",
])

BAD_IMG_PATH  = resolve_img_path([BASE_DIR/"data"/"표돌이.jpeg", BASE_DIR/"표돌이.jpeg"])
GOOD_IMG_PATH = resolve_img_path([BASE_DIR/"data"/"안심.jpeg",  BASE_DIR/"안심.jpeg"])
BAD_IMG_B64   = img_to_base64(BAD_IMG_PATH)
GOOD_IMG_B64  = img_to_base64(GOOD_IMG_PATH)

# =========================================================
# .env 로드
# =========================================================
def get_env_value(key: str) -> str:
    env_map = {}
    if ENV_PATH.exists():
        env_map = dotenv_values(ENV_PATH)
    value = env_map.get(key) or os.environ.get(key, "")
    if isinstance(value, str):
        value = value.strip().strip('"').strip("'")
    return value or ""

OPENAI_API_KEY = get_env_value("OPENAI_API_KEY")
if OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# =========================================================
# 세션 초기화
# =========================================================
defaults = {
    # 챗봇
    "messages":      [],
    "api_messages":  [],
    "chain":         None,
    "rag_ready":     False,
    "rag_error":     "",
    # 간첩 판독 게임
    "spy_q_index":   0,       # 현재 질문 번호 0~3
    "spy_person":    None,    # 현재 지목된 사람
    "spy_history":   [],      # [{"name":..,"question":..,"answer":..,"verdict":..}]
    "spy_phase":     "pick",  # "pick" | "answering" | "verdict"
    "spy_answer_tmp": "",
    "spy_verdict_tmp": None,
    "spy_bad_count":   0,    # 간첩 판정 누적
    "spy_good_count":  0,    # 애국자 판정 누적
    "spy_last_verdict": "none",  # "bad" | "good" | "none"
    # 대피소
    "shelter_df":    None,
    "shelter_error": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================================================
# CSS
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
}
.date-divider-wrapper { display:flex; justify-content:center; margin:6px 0; }
.date-divider {
    color: white; font-size: 12px;
    background-color: rgba(0,0,0,0.2);
    border-radius: 12px; padding: 3px 12px;
}
.msg-row-ai {
    display:flex; align-items:flex-start; gap:8px;
    justify-content:flex-start; margin-bottom:4px;
}
.ai-avatar {
    width:40px; height:40px; border-radius:50%;
    background:linear-gradient(135deg,#2C2C54,#706fd3);
    display:flex; align-items:center; justify-content:center;
    font-size:20px; flex-shrink:0; box-shadow:0 2px 6px rgba(0,0,0,0.2);
}
.ai-name { font-size:12px; color:white; margin-bottom:4px; font-weight:500; }
.bubble-ai {
    background-color:#ffffff; border-radius:0px 16px 16px 16px;
    padding:10px 14px; max-width:72%;
    font-size:14px; font-weight:bold; line-height:1.6;
    color:#1a1a1a; box-shadow:0 1px 4px rgba(0,0,0,0.12); word-break:keep-all;
}
.msg-time-ai {
    font-size:11px; color:rgba(255,255,255,0.8);
    align-self:flex-end; margin-left:4px; white-space:nowrap;
}
.msg-row-user {
    display:flex; align-items:flex-end; gap:6px;
    justify-content:flex-end; margin-bottom:4px;
}
.bubble-user {
    background-color:#FFEB01; border-radius:16px 0px 16px 16px;
    padding:10px 14px; max-width:72%;
    font-size:14px; line-height:1.6; color:#1a1a1a;
    box-shadow:0 1px 4px rgba(0,0,0,0.12); word-break:keep-all;
}
.msg-time-user {
    font-size:11px; color:rgba(255,255,255,0.8);
    align-self:flex-end; white-space:nowrap;
}
#MainMenu {visibility:hidden;} footer {visibility:hidden;} header {visibility:hidden;}
</style>
""", unsafe_allow_html=True)

# =========================================================
# 배경 오버레이 렌더링
# =========================================================
def render_background():
    bad_count  = st.session_state.spy_bad_count
    good_count = st.session_state.spy_good_count
    last       = st.session_state.spy_last_verdict

    if last == "bad" and bad_count > 0 and BAD_IMG_B64:
        opacity = round(min(bad_count / 3, 1.0), 2)
        img_b64 = BAD_IMG_B64
    elif last == "good" and good_count > 0 and GOOD_IMG_B64:
        opacity = round(min(good_count / 3, 1.0), 2)
        img_b64 = GOOD_IMG_B64
    else:
        return

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
def now_time() -> str:
    return datetime.now().strftime("%p %I:%M").replace("AM","오전").replace("PM","오후")

def pick_first_existing(columns, candidates):
    stripped_map = {str(col).strip(): col for col in columns}
    for cand in candidates:
        if cand in stripped_map:
            return stripped_map[cand]
    return None

def extract_region(address: str) -> str:
    address = str(address).strip()
    return address.split()[0] if address else "기타"

def render_bubble(role: str, content: str, time_str: str = ""):
    content_html = html.escape(content).replace("\n", "<br>")
    if role == "assistant":
        st.markdown(f"""
        <div class="msg-row-ai">
            <div class="ai-avatar">🕵️</div>
            <div>
                <div class="ai-name">나락퀴즈쇼</div>
                <div class="bubble-ai">{content_html}</div>
            </div>
            <div class="msg-time-ai">{time_str}</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="msg-row-user">
            <div class="msg-time-user">{time_str}</div>
            <div class="bubble-user">{content_html}</div>
        </div>""", unsafe_allow_html=True)

# =========================================================
# 간첩 판독 판결 함수
# =========================================================
# RAG 벡터스토어 캐시 (evaluate_single 에서 사용)
_rag_retriever_cache = None

def get_rag_retriever():
    global _rag_retriever_cache
    if _rag_retriever_cache is not None:
        return _rag_retriever_cache
    if not PROV_CSV.exists() or not OPENAI_API_KEY:
        return None
    try:
        from langchain_openai import OpenAIEmbeddings
        from langchain_chroma.vectorstores import Chroma
        embedding_model = OpenAIEmbeddings(model="text-embedding-3-small", api_key=OPENAI_API_KEY)
        vector_store = Chroma(
            collection_name="north_korea_events_streamlit",
            embedding_function=embedding_model,
        )
        _rag_retriever_cache = vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 2})
        return _rag_retriever_cache
    except Exception:
        return None


def get_rag_context(question: str, answer: str) -> str:
    """RAG로 관련 과거 도발 사례 최대 2건 가져오기"""
    retriever = get_rag_retriever()
    if retriever is None:
        return ""
    try:
        query = f"{question} {answer}"
        docs = retriever.invoke(query)
        snippets = []
        for doc in docs[:2]:
            lines = doc.page_content.strip().split("\n")
            date  = next((l.replace("Date:","").strip() for l in lines if l.startswith("Date:")), "")
            event = next((l.replace("Event:","").strip() for l in lines if l.startswith("Event:")), "")
            if date and event:
                snippets.append(f"{date} — {event}")
        return "\n".join(snippets)
    except Exception:
        return ""


def evaluate_single(person: str, question: str, answer: str) -> str:
    if not OPENAI_API_KEY:
        return "판결 불가 (API 키 없음)"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        # RAG 컨텍스트 가져오기
        rag_ctx = get_rag_context(question, answer)
        rag_note = f"\n\n참고 과거 사례 (RAG):\n{rag_ctx}" if rag_ctx else ""

        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 안보 전문가입니다. 질문에 대한 답변을 분석해서 "
                        "이 사람이 간첩인지 아닌지 판결합니다.\n\n"
                        "판결 기준:\n"
                        "- 사드 반대, F-35 반대, 한미 동맹 부정, 김정은 옹호/찬양 → 간첩 의심\n"
                        "- 사드 찬성, F-35 찬성, 한미 동맹 긍정, 김정은 비판 → 애국자\n\n"
                        "반드시 아래 형식으로만 답해라:\n"
                        "판결: [간첩] 또는 [애국자]\n"
                        "이유: (한 두 문장, 한국어)\n"
                        "위험도: [매우 위험 / 위험 / 보통 / 안전 / 매우 안전]\n"
                        "근거: (과거 도발 사례를 1~2줄로 인용하며 왜 이 판결을 내렸는지 설명, 한국어)"
                    ),
                },
                {
                    "role": "user",
                    "content": f"피의자: {person}\n질문: {question}\n답변: {answer}{rag_note}",
                },
            ],
            temperature=0.3,
            max_tokens=350,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"판결 오류: {e}"

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
    result = result.dropna(subset=["lat","lon"]).reset_index(drop=True)
    result = result[(result["lat"]!=0)&(result["lon"]!=0)].reset_index(drop=True)
    result["region"] = result["address"].apply(extract_region)
    return result

def build_folium_map(df: pd.DataFrame, max_markers: int = 500) -> folium.Map:
    m = folium.Map(location=[df["lat"].mean(), df["lon"].mean()], zoom_start=12)
    from folium.plugins import MarkerCluster
    cluster = MarkerCluster().add_to(m)
    for _, row in df.head(max_markers).iterrows():
        popup_html = f"<b>{row.get('name','대피소')}</b><br>{row.get('address','')}<br>수용인원: {row.get('capacity','')}"
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
    required_cols = ["Date","Type","Event","Description"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"도발 데이터 CSV에 필요한 컬럼이 없습니다: {missing}")

    docs = []
    for _, row in df.iterrows():
        content = f"Date: {row['Date']}\nType: {row['Type']}\nEvent: {row['Event']}\nDescription: {row['Description']}"
        docs.append(Document(
            page_content=content,
            metadata={"date": str(row["Date"]), "type": str(row["Type"]), "event": str(row["Event"])},
        ))

    embedding_model = OpenAIEmbeddings(model="text-embedding-3-small", api_key=openai_api_key)
    vector_store = Chroma.from_documents(docs, embedding=embedding_model, collection_name="north_korea_events_streamlit")
    retriever = vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 3})

    def format_docs(documents):
        return "\n\n".join(d.page_content for d in documents) if documents else "관련 과거 사례를 찾지 못했습니다."

    prompt = ChatPromptTemplate.from_messages([
        ("system", """
당신은 북한의 과거 도발 사례를 설명하는 분석 도우미이자 전문가입니다.
사용자가 안전불감증 같아 보일 때는 비꼬는 듯한 말투로 답합니다.
사용자가 안보개념이 뚜렷해 보일 때는 친절하게 설명합니다.

규칙
1. 반드시 제공된 context만 근거로 답해라.
2. context 밖의 사실을 지어내지 마라.
3. 반드시 과거 사례를 포함시켜라.
4. 한국어로 작성해라.
5. 이전 대화 맥락도 반영해라.
6. 안보 개념이 없어 보일 때는 비속어도 포함하되 '씨발', '좆', '개새끼'는 제외해라.

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
                st.session_state.shelter_df = prepare_shelter_df(load_csv(str(SHELTER_CSV)))
            except Exception as e:
                st.session_state.shelter_error = str(e)
        else:
            st.session_state.shelter_error = f"대피소 CSV 파일이 없습니다: {SHELTER_CSV.name}"

    if not st.session_state.rag_ready:
        if not PROV_CSV.exists() or not OPENAI_API_KEY:
            st.session_state.rag_error = "도발 데이터 또는 API 키가 없습니다."
            return
        try:
            st.session_state.chain = build_rag_chain(str(PROV_CSV), OPENAI_API_KEY)
            st.session_state.rag_ready = True
        except Exception as e:
            st.session_state.rag_error = str(e)

initialize_resources()
render_background()

# =========================================================
# 사이드바
# =========================================================
with st.sidebar:
    st.title("🎯 나락퀴즈쇼")
    st.divider()

    q_idx = st.session_state.spy_q_index
    st.subheader("🎯 판독 게임 진행 현황")
    st.progress(min(q_idx / len(QUESTIONS), 1.0), text=f"질문 {q_idx} / {len(QUESTIONS)} 진행됨")

    if st.session_state.spy_history:
        st.markdown("**판독 기록**")
        for rec in st.session_state.spy_history:
            is_spy = "[간첩]" in rec["verdict"]
            emoji = "🚨" if is_spy else "🇰🇷"
            st.caption(f"{emoji} {rec['name']} — Q{rec['q_num']}")

    st.divider()
    if st.button("🔄 게임 초기화", use_container_width=True):
        st.session_state.spy_q_index     = 0
        st.session_state.spy_person      = None
        st.session_state.spy_history     = []
        st.session_state.spy_phase       = "pick"
        st.session_state.spy_verdict_tmp = None
        st.session_state.spy_bad_count   = 0
        st.session_state.spy_good_count  = 0
        st.session_state.spy_last_verdict = "none"
        st.rerun()

    if st.button("🗑️ 챗봇 대화 초기화", use_container_width=True):
        st.session_state.messages     = []
        st.session_state.api_messages = []
        st.rerun()

# =========================================================
# 메인 탭
# =========================================================
tab_spy, tab_chat, tab_shelter = st.tabs([
    "🎯 나락 퀴즈쇼",
    "💬 자유 질문 챗봇",
    "🗺️ 민방위 대피소 지도",
])

# =========================================================
# 탭 1: 나락 퀴즈쇼
# =========================================================
with tab_spy:
    st.markdown("""
    <div class="chat-header">
        🎯&nbsp;&nbsp;나락 퀴즈쇼 — 랜덤 지목 후 판독합니다
    </div>
    """, unsafe_allow_html=True)

    # 날짜
    today = (
        datetime.now().strftime("%Y년 %m월 %d일 %A")
        .replace("Monday","월요일").replace("Tuesday","화요일")
        .replace("Wednesday","수요일").replace("Thursday","목요일")
        .replace("Friday","금요일").replace("Saturday","토요일")
        .replace("Sunday","일요일")
    )
    st.markdown(f'<div class="date-divider-wrapper"><div class="date-divider">{today}</div></div>',
                unsafe_allow_html=True)

    q_idx = st.session_state.spy_q_index
    phase = st.session_state.spy_phase

    # 모든 질문 완료
    if q_idx >= len(QUESTIONS):
        st.markdown("""
        <div style="background:linear-gradient(135deg,#2C2C54,#706fd3);
                    color:white;border-radius:16px;padding:30px;text-align:center;margin:20px 0;">
            <div style="font-size:40px;margin-bottom:12px;">🏁</div>
            <div style="font-size:24px;font-weight:bold;">나락 퀴즈쇼 완료!</div>
            <div style="font-size:14px;opacity:0.8;margin-top:8px;">4개 질문이 모두 완료됐습니다</div>
        </div>
        """, unsafe_allow_html=True)

        # 최종 결과 요약
        st.markdown("### 📋 최종 판독 결과")
        for rec in st.session_state.spy_history:
            is_spy = "[간첩]" in rec["verdict"]
            color  = "#8B0000" if is_spy else "#1a5c2a"
            emoji  = "🚨 간첩" if is_spy else "🇰🇷 애국자"
            st.markdown(f"""
            <div style="background:{color};color:white;border-radius:12px;
                        padding:14px 18px;margin-bottom:10px;">
                <b>Q{rec['q_num']}. {rec['name']}</b> → {emoji}<br>
                <span style="font-size:13px;opacity:0.9;">{html.escape(rec['verdict'])}</span>
            </div>
            """, unsafe_allow_html=True)

        if st.button("🔄 처음부터 다시 시작", use_container_width=True):
            st.session_state.spy_q_index      = 0
            st.session_state.spy_person       = None
            st.session_state.spy_history      = []
            st.session_state.spy_phase        = "pick"
            st.session_state.spy_verdict_tmp  = None
            st.session_state.spy_bad_count    = 0
            st.session_state.spy_good_count   = 0
            st.session_state.spy_last_verdict = "none"
            st.rerun()

    # ── PICK: 랜덤 지목 ──────────────────────────────────
    elif phase == "pick":
        st.markdown(f"""
        <div style="background:rgba(44,44,84,0.85);color:white;border-radius:16px;
                    padding:24px;text-align:center;margin:20px 0;">
            <div style="font-size:14px;opacity:0.8;">질문 {q_idx+1} / {len(QUESTIONS)}</div>
            <div style="font-size:18px;font-weight:bold;margin-top:8px;">
                🎲 다음 질문을 받을 사람을 뽑겠습니다!
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🎲 랜덤으로 지목하기!", use_container_width=True):
            st.session_state.spy_person      = random.choice(NAMES)
            st.session_state.spy_phase       = "answering"
            st.session_state.spy_verdict_tmp = None
            st.rerun()

    # ── ANSWERING: 질문 & 답변 ───────────────────────────
    elif phase == "answering":
        person   = st.session_state.spy_person
        question = QUESTIONS[q_idx]

        # 지목 발표 + 상시 다시 뽑기 버튼
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#8B0000,#c0392b);
                        color:white;border-radius:16px;padding:24px;
                        text-align:center;margin:16px 0;
                        box-shadow:0 4px 16px rgba(0,0,0,0.3);">
                <div style="font-size:13px;opacity:0.8;">Q{q_idx+1} 지목된 피의자</div>
                <div style="font-size:36px;font-weight:bold;margin:8px 0;">🎯 {person}</div>
                <div style="font-size:13px;opacity:0.8;">질문에 답해주세요</div>
            </div>
            """, unsafe_allow_html=True)
        with col_b:
            st.markdown("<br><br>", unsafe_allow_html=True)
            if st.button("🎲 다시 뽑기", use_container_width=True, key="repick_answering"):
                st.session_state.spy_person = random.choice(NAMES)
                st.session_state.spy_phase  = "answering"
                st.session_state.spy_verdict_tmp = None
                st.rerun()

        # 질문 말풍선
        render_bubble("assistant", f"Q{q_idx+1}. {question}", now_time())

        st.markdown("<br>", unsafe_allow_html=True)

        with st.form(key=f"spy_answer_{q_idx}", clear_on_submit=True):
            col1, col2 = st.columns([5, 1])
            with col1:
                ans_input = st.text_input(
                    "답변",
                    placeholder=f"{person}님의 답변을 입력하세요...",
                    label_visibility="collapsed",
                )
            with col2:
                submit = st.form_submit_button("➤")

        if submit and ans_input.strip():
            # 답변 저장 후 판결 단계로
            st.session_state.spy_answer_tmp  = ans_input.strip()
            st.session_state.spy_phase       = "verdict"
            st.rerun()

    # ── VERDICT: 판결 ────────────────────────────────────
    elif phase == "verdict":
        person   = st.session_state.spy_person
        question = QUESTIONS[q_idx]
        answer   = st.session_state.spy_answer_tmp

        # 대화 재현
        render_bubble("assistant", f"Q{q_idx+1}. {question}", "")
        render_bubble("user", answer, now_time())

        # 판결 생성
        if st.session_state.spy_verdict_tmp is None:
            with st.spinner("🔍 판결 중..."):
                st.session_state.spy_verdict_tmp = evaluate_single(person, question, answer)
            st.rerun()

        verdict_text = st.session_state.spy_verdict_tmp
        is_spy       = "[간첩]" in verdict_text
        verdict_color = "#8B0000" if is_spy else "#1a5c2a"
        verdict_emoji = "🚨 간첩" if is_spy else "🇰🇷 애국자"

        # 판결 확정 즉시 배경 카운터 업데이트 (버튼 클릭 전에)
        if not st.session_state.get("_bg_updated_for_q", -1) == q_idx:
            if is_spy:
                st.session_state.spy_bad_count   = sum(
                    1 for r in st.session_state.spy_history if "[간첩]" in r["verdict"]
                ) + 1
                st.session_state.spy_last_verdict = "bad"
            else:
                st.session_state.spy_good_count  = sum(
                    1 for r in st.session_state.spy_history if "[간첩]" not in r["verdict"]
                ) + 1
                st.session_state.spy_last_verdict = "good"
            st.session_state["_bg_updated_for_q"] = q_idx
        render_background()

        col_v1, col_v2 = st.columns([3, 1])
        with col_v2:
            if st.button("🎲 다시 뽑기", use_container_width=True, key="repick_verdict"):
                st.session_state.spy_person      = random.choice(NAMES)
                st.session_state.spy_phase       = "answering"
                st.session_state.spy_verdict_tmp = None
                st.session_state["_bg_updated_for_q"] = -1
                st.rerun()
        with col_v1:
            pass

        st.markdown(f"""
        <div style="background:{verdict_color};color:white;border-radius:16px;
                    padding:24px;text-align:center;margin:16px 0;
                    box-shadow:0 4px 16px rgba(0,0,0,0.3);">
            <div style="font-size:13px;opacity:0.8;">{person} 판결 결과</div>
            <div style="font-size:36px;margin:8px 0;">{'🚨' if is_spy else '🇰🇷'}</div>
            <div style="font-size:24px;font-weight:bold;">{verdict_emoji}</div>
        </div>
        <div style="background:white;color:#1a1a1a;border-radius:16px;
                    padding:16px 20px;font-size:14px;font-weight:bold;
                    line-height:1.8;margin-bottom:20px;">
            {html.escape(verdict_text).replace(chr(10), "<br>")}
        </div>
        """, unsafe_allow_html=True)

        # 기록 저장 후 다음 질문으로
        next_label = "다음 질문으로 →" if q_idx + 1 < len(QUESTIONS) else "최종 결과 보기 🏁"
        if st.button(f"✅ {next_label}", use_container_width=True):
            st.session_state.spy_history.append({
                "q_num":    q_idx + 1,
                "name":     person,
                "question": question,
                "answer":   answer,
                "verdict":  verdict_text,
            })
            st.session_state.spy_q_index    += 1
            st.session_state.spy_person      = None
            st.session_state.spy_phase       = "pick"
            st.session_state.spy_verdict_tmp = None
            st.rerun()

# =========================================================
# 탭 2: 자유 질문 챗봇
# =========================================================
with tab_chat:
    st.markdown("""
    <div class="chat-header">
        💬&nbsp;&nbsp;자유 질문 챗봇
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f'<div class="date-divider-wrapper"><div class="date-divider">{today}</div></div>',
                unsafe_allow_html=True)

    if not st.session_state.rag_ready:
        st.warning("RAG가 아직 준비되지 않았습니다.")
    else:
        if not st.session_state.messages:
            welcome = "안녕하세요! 북한 도발 관련 질문이 있으시면 편하게 물어보세요 🕵️"
            st.session_state.messages.append({"role":"assistant","content":welcome,"time":now_time()})

        for msg in st.session_state.messages:
            render_bubble(msg["role"], msg["content"], msg["time"])

        st.markdown("<br>", unsafe_allow_html=True)

        with st.form(key="chat_form", clear_on_submit=True):
            col1, col2 = st.columns([5, 1])
            with col1:
                user_text = st.text_input("메시지", placeholder="질문을 입력하세요...", label_visibility="collapsed")
            with col2:
                send_btn = st.form_submit_button("➤")

        if send_btn and user_text.strip():
            user_input = user_text.strip()
            t = now_time()
            st.session_state.messages.append({"role":"user","content":user_input,"time":t})
            history_text = "\n".join([
                f"{'사용자' if m['role']=='user' else 'AI'}: {m['content']}"
                for m in st.session_state.messages[-8:]
            ])
            with st.spinner("분석 중..."):
                try:
                    answer = st.session_state.chain.invoke({"question":user_input,"chat_history":history_text})
                except Exception as e:
                    answer = f"오류: {e}"
            st.session_state.messages.append({"role":"assistant","content":answer,"time":now_time()})
            st.rerun()

# =========================================================
# 탭 3: 민방위 대피소 지도
# =========================================================
with tab_shelter:
    if st.session_state.shelter_df is None:
        st.error("대피소 데이터를 불러오지 못했습니다.")
    else:
        st.write("민방위대피시설 데이터를 기준으로 지도에 대피소를 표시합니다.")
        shelter_df = st.session_state.shelter_df.copy()

        c1, c2 = st.columns([2, 1])
        with c1:
            keyword = st.text_input("시설명/주소 검색", placeholder="예: 강남구, 종로구")
        with c2:
            regions = sorted([r for r in shelter_df["region"].dropna().unique() if r])
            selected_region = st.selectbox("지역 선택", options=["전체"] + regions)

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
            st_folium(build_folium_map(shelter_df), width="100%", height=650)