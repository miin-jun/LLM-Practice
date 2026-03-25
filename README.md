# 🛡️ 전쟁불감증 퇴치기

북한의 과거 도발 사례를 RAG 기반으로 분석하고, 전국 민방위 대피소를 지도에서 확인할 수 있는 Streamlit 웹 애플리케이션입니다.

---

## 📌 주요 기능

- **도발 분석 챗봇**: 북한의 과거 도발 사례 데이터를 기반으로 질문에 답변합니다. 사용자의 안보 의식 수준에 따라 말투가 달라집니다.
- **민방위 대피소 지도**: 전국 민방위 대피시설을 Folium 지도 위에 클러스터 마커로 표시합니다. 시설명·주소 검색 및 지역 필터를 지원합니다.

---


## 📊 데이터 명세

### `north_korea_events_전처리.csv` — 북한 도발 사례

| 컬럼 | 설명 |
|------|------|
| `Date` | 사건 발생 날짜 |
| `Type` | 도발 유형 (미사일, 핵실험 등) |
| `Event` | 사건명 |
| `Description` | 사건 상세 설명 |

### `민방위대피시설_전처리.csv` — 민방위 대피소

| 컬럼 | 설명 |
|------|------|
| `시설명` | 대피소 이름 |
| `소재지전체주소` | 전체 주소 |
| `최대수용인원` | 수용 가능 인원 |
| `위도(EPSG4326)` | 위도 좌표 |
| `경도(EPSG4326)` | 경도 좌표 |

---

## 🧠 RAG 구조

```
사용자 질문
    ↓
OpenAI text-embedding-3-small (임베딩)
    ↓
Chroma 벡터 스토어 (유사도 검색, k=3)
    ↓
관련 도발 사례 context 추출
    ↓
GPT-4.1-mini (답변 생성)
    ↓
사용자에게 출력
```

- 모델: `gpt-4.1-mini` (temperature=0.2)
- 임베딩: `text-embedding-3-small`
- 벡터 DB: `Chroma` (in-memory)
- 이전 대화 최대 8턴 반영

---

## 🗺️ 대피소 지도

- **라이브러리**: Folium + streamlit-folium
- **필터**: 지역 선택(시·도 단위) + 시설명/주소 키워드 검색

---
## 자료 출처 
- 북한 도발 사례 : https://beyondparallel.csis.org/database-north-korean-provocations/?utm_source=chatgpt.com
- 민방위 대피소 : https://www.data.go.kr/data/15044951/fileData.do#
