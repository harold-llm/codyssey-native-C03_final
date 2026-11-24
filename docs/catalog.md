# RAG 콘텐츠 카탈로그 안내

> **자동 생성 문서입니다. 직접 고치지 마세요.** 원본은 `backend/data/catalog.json`(추천 대상 항목)과
> `backend/data/content_guide.json`(설명·찾는 법·학습 단위)이며, `python3 scripts/gen_catalog_doc.py`로 다시 만듭니다.
> 두 파일을 바꾼 커밋은 pre-commit 훅이 이 문서를 자동으로 갱신합니다.

## 한눈에 보기

- 꽃피다는 콘텐츠를 직접 제공하지 않습니다. 부모가 이미 갖고 있거나 쉽게 구할 수 있는 **외부 자료**(책·앱·영상) 중
  **무엇을, 어느 부분을, 어떻게** 할지 매일 카드로 알려 줍니다. 아래 목록이 그 추천 후보 전체입니다.
- 온보딩 4주 계획은 이 카탈로그에서 RAG 검색(나이·레벨·하루 시간·보유 교재 필터 + TF-IDF)으로 후보를 찾고,
  Claude가 후보 ID 안에서만 20일 순서를 정합니다. 후보 밖의 자료는 추천할 수 없습니다.
- 항목 **67개**, 시리즈·서비스 **31종**, 출처를 확인한 학습 단위 **229개** (책 한 권 또는 소리 묶음 하나)

| 구체성 | 항목 수 | 뜻 |
|---|---|---|
| 학습 단위 | 14 | 학습 단위 — 권·에피소드 순서가 지정됨 |
| 단일 작품 | 17 | 단일 작품 — 노래·책·영상 한 편이 지정됨 |
| 묶음 | 36 | 묶음 — 앱·시리즈 전체라서 무엇을 할지 아직 지정되지 않음 (학습 단위로 쪼갤 대상) |

레벨: L1 노출·듣기 → L2 소리 인지 → L3 파닉스 → L4 사이트워드·초기 해독 → L5 리더스 독해

## 시리즈·서비스별 안내

처음 보는 자료라면 여기서 '이게 무엇인지'부터 확인하세요.

### ABCmouse

*유료 학습 앱* · 비용: 유료 구독 · [공식 사이트](https://www.abcmouse.com/)

미국 Age of Learning의 2~8세 유료 학습 앱. 단계별 '학습 경로(Step-by-Step Learning Path)'로 진행한다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `abcmouse` | ABCmouse - Early Learning | 4~5세 | L1 | 앱·활동·듣기 | 10분 | 묶음 | ABCmouse 앱 → 학습 경로의 다음 레슨 |
| `abcmouse-full` | ABCmouse - Full Curriculum | 4~7세 | L1 | 앱·활동·듣기 | 10분 | 묶음 | ABCmouse 앱 전체 — 학습 경로의 다음 레슨 |

### Cocomelon

*유튜브 동요 채널* · 비용: 무료 (공식 유튜브) · [공식 사이트](https://cocomelon.com/)

3D 애니메이션 동요 채널. 일상 루틴(목욕·잠자기 등)을 노래로 다룬다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `cocomelon` | Cocomelon - Nursery Rhymes | 4~5세 | L1 | 영상·듣기 | 10분 | 묶음 | Cocomelon 유튜브에서 동요 한 곡 (예: 'Wheels on the Bus') |

### Eric Carle 그림책

*종이 그림책 (단권)* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://eric-carle.com/)

에릭 칼의 대표 그림책. 반복 문장과 큰 그림 덕분에 영어 그림책 첫 권으로 자주 추천된다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `eric-brownbear` | Eric Carle - Brown Bear, Brown Bear, What Do You See? | 4~5세 | L1 | 리더스·그림책·듣기 | 10분 | 단일 작품 | 그림책 『Brown Bear, Brown Bear, What Do You See?』 (Bill Martin Jr. 글, Eric Carle 그림) |
| `eric-caterpillar` | Eric Carle - The Very Hungry Caterpillar | 4~5세 | L1 | 리더스·그림책·듣기 | 10분 | 단일 작품 | 그림책 『The Very Hungry Caterpillar』 (서점·도서관) |

### Jolly Phonics

*영국 파닉스 프로그램* · 비용: 교재·음원 구입 · [공식 사이트](https://www.jollylearning.co.uk/)

영국 학교에서 널리 쓰는 합성 파닉스 프로그램. 42개 소리를 7개 그룹으로 가르치며, 소리마다 노래와 동작이 있다. 첫 그룹은 s, a, t, i, p, n.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `jolly-songs` | Jolly Phonics - Songs | 4~5세 | L1 | 오디오·듣기 | 10분 | 학습 단위 | Jolly Phonics 노래 음원 — 7그룹 순서대로, 하루 소리 3개 |
| `jolly-full` | Jolly Phonics - Full Program | 4~7세 | L2 | 파닉스·읽기 | 15분 | 학습 단위 | Jolly Phonics 전 과정 — 7그룹 42개 소리를 순서대로 |
| `jolly-letter` | Jolly Phonics - Letter Sounds | 5~6세 | L2 | 파닉스·읽기 | 15분 | 학습 단위 | Jolly Phonics 교재 — 7그룹 42개 소리를 순서대로, 하루 소리 3개 |

<details><summary><code>jolly-songs</code> 학습 단위 14개 (진행 순서)</summary>

- **Group 1**
  1. s · a · t
  2. i · p · n
- **Group 2**
  3. c k · e · h
  4. r · m · d
- **Group 3**
  5. g · o · u
  6. l · f · b
- **Group 4**
  7. ai · j · oa
  8. ie · ee · or
- **Group 5**
  9. z · w · ng
  10. v · oo (짧게) · oo (길게)
- **Group 6**
  11. y · x · ch
  12. sh · th (약하게) · th (강하게)
- **Group 7**
  13. qu · ou · oi
  14. ue · er · ar

</details>

<details><summary><code>jolly-letter</code> 학습 단위 14개 (진행 순서)</summary>

- **Group 1**
  1. s · a · t
  2. i · p · n
- **Group 2**
  3. c k · e · h
  4. r · m · d
- **Group 3**
  5. g · o · u
  6. l · f · b
- **Group 4**
  7. ai · j · oa
  8. ie · ee · or
- **Group 5**
  9. z · w · ng
  10. v · oo (짧게) · oo (길게)
- **Group 6**
  11. y · x · ch
  12. sh · th (약하게) · th (강하게)
- **Group 7**
  13. qu · ou · oi
  14. ue · er · ar

</details>

<details><summary><code>jolly-full</code> 학습 단위 14개 (진행 순서)</summary>

- **Group 1**
  1. s · a · t
  2. i · p · n
- **Group 2**
  3. c k · e · h
  4. r · m · d
- **Group 3**
  5. g · o · u
  6. l · f · b
- **Group 4**
  7. ai · j · oa
  8. ie · ee · or
- **Group 5**
  9. z · w · ng
  10. v · oo (짧게) · oo (길게)
- **Group 6**
  11. y · x · ch
  12. sh · th (약하게) · th (강하게)
- **Group 7**
  13. qu · ou · oi
  14. ue · er · ar

</details>

### Khan Academy Kids

*무료 학습 앱* · 비용: 무료 앱 · [공식 사이트](https://learn.khanacademy.org/khan-academy-kids/)

비영리 칸아카데미의 2~8세용 무료 앱. 앱 안의 '학습 경로(Learning Path)'가 아이 수준에 맞춰 활동을 차례로 제시한다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `khan-full` | Khan Academy Kids - Full Curriculum | 4~7세 | L1 | 앱·활동·듣기 | 10분 | 묶음 | Khan Academy Kids 앱 전체 — 학습 경로의 다음 활동 |
| `khan-kids` | Khan Academy Kids | 4~5세 | L1 | 앱·활동·듣기 | 10분 | 묶음 | Khan Academy Kids 앱 → 아이 프로필 → 학습 경로(Learning Path)의 다음 활동 |

### Peppa Pig (페파 피그)

*영국 애니메이션* · 비용: 무료 (공식 유튜브) · [공식 사이트](https://www.peppapig.com/)

꼬마 돼지 페파의 일상을 다룬 영국 애니메이션. 한 편이 약 5분이라 하루 한 편씩 보기 좋고, 가족·놀이 같은 일상 표현이 반복된다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `peppa` | Peppa Pig - Official Episodes | 4~5세 | L1 | 영상·듣기 | 10분 | 학습 단위 | 유튜브에서 'Peppa Pig + 에피소드 제목' 검색 → 공식 채널 영상인지 확인 — Series 1을 방송 순서대로 |

<details><summary><code>peppa</code> 학습 단위 52개 (진행 순서)</summary>

- **Series 1**
  1. Muddy Puddles
  2. Mr Dinosaur Is Lost
  3. Best Friend
  4. Polly Parrot
  5. Hide and Seek
  6. The Playgroup
  7. Mummy Pig at Work
  8. Piggy in the Middle
  9. Daddy Loses His Glasses
  10. Gardening
  11. Hiccups
  12. Bicycles
  13. Secrets
  14. Flying a Kite
  15. Picnic
  16. Musical Instruments
  17. Frogs and Worms and Butterflies
  18. Dressing Up
  19. New Shoes
  20. The School Fete
  21. Mummy Pig's Birthday
  22. The Tooth Fairy
  23. The New Car
  24. Treasure Hunt
  25. Not Very Well
  26. Snow
  27. Windy Castle
  28. My Cousin Chloé
  29. Pancakes
  30. Babysitting
  31. Ballet Lesson
  32. Thunderstorm
  33. Cleaning the Car
  34. Lunch
  35. Camping
  36. The Sleepy Princess
  37. The Tree House
  38. Fancy Dress Party
  39. The Museum
  40. Very Hot Day
  41. Chloé's Puppet Show
  42. Daddy Gets Fit
  43. Tidying Up
  44. The Playground
  45. Daddy Puts up a Picture
  46. At the Beach
  47. Mister Skinnylegs
  48. Grandpa Pig's Boat
  49. Shopping
  50. My Birthday Party
  51. Daddy's Movie Camera
  52. School Play

</details>

### Pinkfong (핑크퐁)

*유튜브 동요 채널* · 비용: 무료 (공식 유튜브) · [공식 사이트](https://www.pinkfong.com/)

한국 더핑크퐁컴퍼니의 영어 동요 채널. 'Baby Shark'가 대표곡이다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `pinkfong-babyshark` | Pinkfong - Baby Shark | 4~5세 | L1 | 영상·듣기 | 10분 | 단일 작품 | 핑크퐁 유튜브에서 'Baby Shark Dance' 검색 |

### Starfall

*파닉스·읽기 웹사이트/앱* · 비용: 일부 무료, 나머지 유료 회원제 · [공식 사이트](https://www.starfall.com/)

미국 유아·초등 저학년용 읽기 사이트. 알파벳(ABCs) → 읽기 배우기(Learn to Read) → 나는 읽는다(I'm Reading) 순서로 메뉴가 나뉜다. 일부는 무료, 나머지는 회원제.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `starfall-abcs` | Starfall - ABCs | 4~5세 | L1 | 앱·활동·읽기 | 10분 | 묶음 | starfall.com → ABCs 메뉴 → 알파벳 한 글자씩 (A부터) |
| `starfall-full` | Starfall - Full Curriculum | 4~7세 | L2 | 앱·활동·읽기 | 10분 | 묶음 | starfall.com 전체 — 메뉴가 지정되지 않음 |
| `starfall-read` | Starfall - Learn to Read | 5~6세 | L2 | 앱·활동·읽기 | 10분 | 묶음 | starfall.com → Learn to Read 메뉴의 Zac the Rat부터 차례로 |
| `starfall-imreading` | Starfall - I'm Reading | 6~7세 | L3 | 앱·활동·읽기 | 10분 | 묶음 | starfall.com → I'm Reading 메뉴의 이야기 한 편 |

### Super Simple Songs

*유튜브 동요 채널* · 비용: 무료 (공식 유튜브) · [공식 사이트](https://supersimple.com/)

캐나다 Super Simple이 만든 유아 영어 동요 채널. 느린 박자와 율동이 있어 처음 영어를 듣는 4~5세에게 많이 쓰인다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `sss-abc` | Super Simple Songs - ABC Song | 4~5세 | L1 | 영상·듣기 | 10분 | 단일 작품 | Super Simple Songs 유튜브에서 'ABC Song' 검색 |
| `sss-head` | Super Simple Songs - Head Shoulders Knees & Toes | 4~5세 | L1 | 영상·듣기 | 10분 | 단일 작품 | Super Simple Songs 유튜브에서 'Head Shoulders Knees & Toes' 검색 |
| `sss-library` | Super Simple Songs - Full Library | 4~7세 | L1 | 영상·듣기 | 10분 | 묶음 | Super Simple Songs 유튜브 전체 — 곡이 지정되지 않음 |
| `sss-twinkle` | Super Simple Songs - Twinkle Twinkle Little Star | 4~5세 | L1 | 영상·듣기 | 10분 | 단일 작품 | Super Simple Songs 유튜브에서 'Twinkle Twinkle Little Star' 검색 |
| `sss-phonics` | Super Simple Songs - Phonics Song | 5~6세 | L2 | 영상·읽기 | 10분 | 단일 작품 | Super Simple Songs 유튜브에서 'Phonics Song' 검색 |

### Usborne (어스본)

*영국 출판사의 유아 그림책·리더스* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://usborne.com/)

영국 어린이책 출판사. 'That's not my...' 촉감책, 'Phonics Readers' 파닉스 리더스, 'First Reading' 단계별 리더스가 있다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `usborne-thatsnotmy` | Usborne - That's Not My... series | 4~5세 | L1 | 리더스·그림책·듣기 | 10분 | 묶음 | 'That's not my...' 촉감책 중 아무 권 (예: 『That's not my puppy...』) |
| `usborne-fox` | Usborne Phonics Readers - Fox on a Box | 5~6세 | L2 | 리더스·그림책·읽기 | 15분 | 단일 작품 | Usborne Phonics Readers 『Fox on a Box』 |
| `usborne-full` | Usborne - Full Phonics Collection | 4~7세 | L2 | 리더스·그림책·읽기 | 15분 | 묶음 | Usborne 파닉스 리더스 전체 — 권이 지정되지 않음 |
| `usborne-first` | Usborne - First Reading Level 1 | 6~7세 | L3 | 리더스·그림책·읽기 | 15분 | 묶음 | Usborne First Reading Level 1 책 중 1권 |

### 직접 만드는 카드·워크시트

*가정용 교구 (출판물 아님)* · 비용: 무료 (직접 만들거나 무료 출력물)

특정 출판물이 아니라 부모가 출력하거나 만들어 쓰는 카드·쓰기 활동. 무료 출력물을 써도 된다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `action-cards` | Action Verb Cards | 4~5세 | L1 | 앱·활동·말하기 | 10분 | 단일 작품 | 동작 단어(jump, run, clap, sit 등) 카드를 직접 만들거나 무료 출력물 사용 |
| `color-flashcards` | Color & Shape Flashcards | 4~5세 | L1 | 앱·활동·말하기 | 10분 | 단일 작품 | 색깔·모양 카드를 직접 만들거나 무료 출력물 사용 |
| `sight-cards` | Sight Word Flashcards | 5~6세 | L2 | 앱·활동·읽기 | 10분 | 단일 작품 | 사이트워드(the, a, I, is, see, can 등) 카드를 직접 만들거나 무료 출력물 사용 |
| `cvc-writing` | CVC Word Writing Practice | 6~7세 | L3 | 워크시트·쓰기 | 15분 | 단일 작품 | CVC 단어(cat, dog, sun 등) 따라 쓰기 — 직접 만들거나 무료 출력물 사용 |

### Alphablocks

*영국 BBC 파닉스 애니메이션* · 비용: 무료 (공식 유튜브) · [공식 사이트](https://www.learningblocks.tv/)

알파벳 블록 캐릭터가 합쳐지며 단어 소리를 만드는 BBC CBeebies 애니메이션. 에피소드마다 한두 개 소리를 다룬다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `alphablocks` | Alphablocks - Phonics Episodes | 5~6세 | L2 | 영상·읽기 | 10분 | 묶음 | Alphablocks 공식 유튜브 → Series 1 에피소드부터 |

### Bob Books

*미국 파닉스 리더스 세트* · 비용: 책 구입 · [공식 사이트](https://bobbooks.com/)

아주 짧은 문장으로 된 미국 파닉스 소책자 세트. Set 1은 짧은 모음 단어(CVC)만으로 읽기를 시작한다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `bobbooks-1` | Bob Books - Set 1: Beginning Readers | 5~6세 | L2 | 리더스·그림책·읽기 | 15분 | 묶음 | Bob Books Set 1 소책자 1권부터 차례로 |
| `bobbooks-2` | Bob Books - Set 2: Advancing Beginners | 6~7세 | L3 | 리더스·그림책·읽기 | 15분 | 묶음 | Bob Books Set 2 소책자 1권부터 차례로 |

### Dr. Seuss

*종이 그림책 (단권)* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://www.seussville.com/)

라임(운율)으로 유명한 미국 그림책 작가. 'Hop on Pop'은 짧은 운율 단어로 된 초기 읽기 책이다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `drseuss-hop` | Dr. Seuss - Hop on Pop | 5~6세 | L2 | 리더스·그림책·읽기 | 15분 | 단일 작품 | 그림책 『Hop on Pop』 (Dr. Seuss, Bright and Early Books) |

### LeapFrog Letter Factory

*알파벳 소리 애니메이션 (단편)* · 비용: 영상 구입 또는 대여 · [공식 사이트](https://www.leapfrog.com/)

알파벳 26자의 소리를 공장 이야기로 소개하는 약 35분짜리 애니메이션. 짧게 나눠 본다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `leapfrog-letter` | LeapFrog - Letter Factory | 5~6세 | L2 | 영상·읽기 | 10분 | 단일 작품 | 『LeapFrog: Letter Factory』 영상을 5~10분씩 나눠 보기 |

### Oxford Reading Tree (ORT)

*영국 옥스퍼드대출판부(OUP) 단계별 리더스* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://home.oxfordowl.co.uk/)

Biff·Chip·Kipper 남매와 강아지 Floppy가 나오는 영국 대표 리더스. Stage 1(글 없는 책)부터 단계가 올라가며, 한 단계는 여러 '팩'(각 6권)으로 구성된다. 국내에서 '옥스포드 리딩 트리'로 많이 팔린다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `ort-stage1` | Oxford Reading Tree - Stage 1 | 5~6세 | L2 | 리더스·그림책·읽기 | 15분 | 묶음 | ORT Stage 1(글 없는 책)·Stage 1+(첫 문장) 팩. 권별 제목은 공식 목록 확인 후 학습 단위로 추가 예정 |
| `ort-full` | Oxford Reading Tree - Full Series | 4~7세 | L3 | 리더스·그림책·읽기 | 15분 | 학습 단위 | 집에 있는 ORT 전집을 Stage 2부터 차례로 — 권 순서는 카드가 매일 안내해요 |
| `ort-stage2` | Oxford Reading Tree - Stage 2 | 5~6세 | L3 | 리더스·그림책·읽기 | 15분 | 학습 단위 | ORT Stage 2 팩 6종(36권) — 권 순서는 카드가 매일 안내해요 |
| `ort-stage3` | Oxford Reading Tree - Stage 3 | 6~7세 | L3 | 리더스·그림책·읽기 | 15분 | 학습 단위 | ORT Stage 3 팩 5종(30권) — 권 순서는 카드가 매일 안내해요 |
| `ort-stage4` | Oxford Reading Tree - Stage 4 | 6~7세 | L4 | 리더스·그림책·읽기 | 15분 | 학습 단위 | ORT Stage 4 Decode and Develop 팩(6권) — 권 순서는 카드가 매일 안내해요 |
| `ort-stage5` | Oxford Reading Tree - Stage 5 | 6~7세 | L5 | 리더스·그림책·읽기 | 15분 | 학습 단위 | ORT Stage 5 Decode and Develop 팩(6권) — 권 순서는 카드가 매일 안내해요 |

<details><summary><code>ort-stage2</code> 학습 단위 36개 (진행 순서)</summary>

- **Stage 2 First Sentences**
  1. The Big Egg
  2. Poor Floppy
  3. Put It Back
  4. In a Bit
  5. A Present for Mum
  6. The Hole in the Sand
- **Stage 2 Stories**
  7. The Toys' Party
  8. New Trainers
  9. A New Dog
  10. What a Bad Dog!
  11. The Go-kart
  12. The Dream
- **Stage 2 Patterned Stories**
  13. Monkey Tricks
  14. Hey Presto!
  15. It's the Weather
  16. Naughty Children
  17. A Sinking Feeling
  18. Creepy-crawly!
- **Stage 2 More Patterned Stories A**
  19. What Is It?
  20. The Lost Puppy
  21. New Trees
  22. Up and Down
  23. The Little Dragon
  24. The Band
- **Stage 2 More Stories A**
  25. Floppy's Bath
  26. The Baby-sitter
  27. The Water Fight
  28. Kipper's Balloon
  29. Spots!
  30. Kipper's Birthday
- **Stage 2 More Stories B**
  31. Kipper's Laces
  32. The Wobbly Tooth
  33. The Foggy Day
  34. Biff's Aeroplane
  35. Floppy the Hero
  36. The Chase

</details>

<details><summary><code>ort-stage3</code> 학습 단위 30개 (진행 순서)</summary>

- **Stage 3 First Sentences**
  1. The Duck Race
  2. Sniff
  3. Pond Dipping
  4. The Ice Rink
  5. The Mud Bath
  6. The Steel Band
- **Stage 3 Stories**
  7. On the Sand
  8. The Egg Hunt
  9. Nobody Wanted to Play
  10. A Cat in the Tree
  11. The Rope Swing
  12. By the Stream
- **Stage 3 More Stories A**
  13. Kipper the Clown
  14. Strawberry Jam
  15. The Jumble Sale
  16. At the Seaside
  17. Kipper's Idea
  18. The Snowman
- **Stage 3 More Stories B**
  19. The Barbecue
  20. The Carnival
  21. At the Pool
  22. Bull's-eye!
  23. Book Week
  24. The Cold Day
- **Stage 3 Decode and Develop**
  25. Floppy and the Puppets
  26. Monkeys on the Car
  27. Dragons!
  28. The Enormous Picture
  29. Gran and the Go-karts
  30. Helicopter Rescue

</details>

<details><summary><code>ort-stage4</code> 학습 단위 6개 (진행 순서)</summary>

- **Stage 4 Decode and Develop**
  1. The Stars
  2. Long Legs
  3. Floppy and the Skateboard
  4. Gran's New Glasses
  5. The Birthday Candle
  6. The Seal Pup

</details>

<details><summary><code>ort-stage5</code> 학습 단위 6개 (진행 순서)</summary>

- **Stage 5 Decode and Develop**
  1. Highland Games
  2. The Orchid Thief
  3. Rats!
  4. A Pet Called Cucumber
  5. Bush Fire!
  6. Bessie's Flying Circus

</details>

<details><summary><code>ort-full</code> 학습 단위 78개 (진행 순서)</summary>

- **Stage 2 First Sentences**
  1. The Big Egg
  2. Poor Floppy
  3. Put It Back
  4. In a Bit
  5. A Present for Mum
  6. The Hole in the Sand
- **Stage 2 Stories**
  7. The Toys' Party
  8. New Trainers
  9. A New Dog
  10. What a Bad Dog!
  11. The Go-kart
  12. The Dream
- **Stage 2 Patterned Stories**
  13. Monkey Tricks
  14. Hey Presto!
  15. It's the Weather
  16. Naughty Children
  17. A Sinking Feeling
  18. Creepy-crawly!
- **Stage 2 More Patterned Stories A**
  19. What Is It?
  20. The Lost Puppy
  21. New Trees
  22. Up and Down
  23. The Little Dragon
  24. The Band
- **Stage 2 More Stories A**
  25. Floppy's Bath
  26. The Baby-sitter
  27. The Water Fight
  28. Kipper's Balloon
  29. Spots!
  30. Kipper's Birthday
- **Stage 2 More Stories B**
  31. Kipper's Laces
  32. The Wobbly Tooth
  33. The Foggy Day
  34. Biff's Aeroplane
  35. Floppy the Hero
  36. The Chase
- **Stage 3 First Sentences**
  37. The Duck Race
  38. Sniff
  39. Pond Dipping
  40. The Ice Rink
  41. The Mud Bath
  42. The Steel Band
- **Stage 3 Stories**
  43. On the Sand
  44. The Egg Hunt
  45. Nobody Wanted to Play
  46. A Cat in the Tree
  47. The Rope Swing
  48. By the Stream
- **Stage 3 More Stories A**
  49. Kipper the Clown
  50. Strawberry Jam
  51. The Jumble Sale
  52. At the Seaside
  53. Kipper's Idea
  54. The Snowman
- **Stage 3 More Stories B**
  55. The Barbecue
  56. The Carnival
  57. At the Pool
  58. Bull's-eye!
  59. Book Week
  60. The Cold Day
- **Stage 3 Decode and Develop**
  61. Floppy and the Puppets
  62. Monkeys on the Car
  63. Dragons!
  64. The Enormous Picture
  65. Gran and the Go-karts
  66. Helicopter Rescue
- **Stage 4 Decode and Develop**
  67. The Stars
  68. Long Legs
  69. Floppy and the Skateboard
  70. Gran's New Glasses
  71. The Birthday Candle
  72. The Seal Pup
- **Stage 5 Decode and Develop**
  73. Highland Games
  74. The Orchid Thief
  75. Rats!
  76. A Pet Called Cucumber
  77. Bush Fire!
  78. Bessie's Flying Circus

</details>

### Pete the Cat

*종이 그림책 (단권)* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://www.petethecatbooks.com/)

파란 고양이 피트가 노래하며 반복 문장을 들려주는 그림책 시리즈. 노래 영상과 같이 쓰기 좋다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `pete-shoes` | Pete the Cat - I Love My White Shoes | 5~6세 | L2 | 리더스·그림책·읽기 | 15분 | 단일 작품 | 그림책 『Pete the Cat: I Love My White Shoes』 |
| `pete-school` | Pete the Cat - Rocking in My School Shoes | 6~7세 | L3 | 리더스·그림책·읽기 | 15분 | 단일 작품 | 그림책 『Pete the Cat: Rocking in My School Shoes』 |

### Raz-Kids

*유료 레벨별 전자책 앱* · 비용: 유료 구독 · [공식 사이트](https://www.raz-kids.com/)

미국 Learning A-Z의 레벨별 전자책 앱. aa → A → B → C … 순서로 레벨이 올라가며, 듣기·읽기·퀴즈가 붙어 있다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `razkids-aa` | Raz-Kids - Level aa-A | 5~6세 | L2 | 앱·활동·읽기 | 10분 | 묶음 | Raz-Kids 앱 → Level aa 책부터 차례로, 그다음 Level A |
| `razkids-bc` | Raz-Kids - Level B-C | 6~7세 | L3 | 앱·활동·읽기 | 10분 | 묶음 | Raz-Kids 앱 → Level B 책부터 차례로, 그다음 Level C |
| `razkids-full` | Raz-Kids - Full Library | 4~7세 | L3 | 앱·활동·읽기 | 10분 | 묶음 | Raz-Kids 앱 전체 — 레벨이 지정되지 않음 |

### Reading Eggs

*유료 읽기 학습 앱* · 비용: 유료 구독 (무료 체험 있음) · [공식 사이트](https://readingeggs.com/)

호주의 읽기 학습 앱. 지도(Map) 위의 레슨을 1번부터 차례로 진행한다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `readingeggs` | Reading Eggs | 5~6세 | L2 | 앱·활동·읽기 | 10분 | 묶음 | Reading Eggs 앱 → 지도(Map)의 다음 레슨 |
| `readingeggs-full` | Reading Eggs - Full Program | 4~7세 | L2 | 앱·활동·읽기 | 10분 | 묶음 | Reading Eggs 앱 전체 — 지도의 다음 레슨 |

### Scholastic

*미국 어린이 출판사* · 비용: 책 구입 · [공식 사이트](https://www.scholastic.com/)

미국 최대 어린이 출판사. 파닉스 워크북, 사이트워드 리더스 등 유아 교재가 많다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `scholastic-phonics` | Scholastic - Phonics Workbook | 5~6세 | L2 | 워크시트·쓰기 | 15분 | 묶음 | Scholastic 파닉스 워크북 — 첫 장부터 하루 2~3쪽 |
| `scholastic-full` | Scholastic - Full Collection | 4~7세 | L3 | 리더스·그림책·읽기 | 15분 | 묶음 | Scholastic 유아 교재 전체 — 권이 지정되지 않음 |
| `scholastic-sight` | Scholastic - Sight Word Readers | 6~7세 | L3 | 리더스·그림책·읽기 | 15분 | 묶음 | Scholastic Sight Word Readers 세트 1권부터 |

### Elephant & Piggie (Mo Willems)

*종이 그림책 (단권)* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://www.mowillems.com/)

코끼리 Gerald와 돼지 Piggie의 말풍선 대화로만 된 Mo Willems의 초기 리더스 25권(2007~2016). 문장이 짧고 반복돼 역할을 나눠 읽기 좋고, 미국 도서관협회 Geisel상을 여러 번 받았다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `elephant-fly` | Elephant & Piggie - Today I Will Fly! | 6~7세 | L3 | 리더스·그림책·읽기 | 15분 | 단일 작품 | 그림책 『Today I Will Fly!』 (An Elephant & Piggie Book) |
| `elephant-piggie` | Elephant & Piggie - Full Series (25 books) | 5~7세 | L3 | 리더스·그림책·읽기 | 15분 | 학습 단위 | Elephant & Piggie 25권을 출간 순서대로 (1권 『Today I Will Fly!』) |

<details><summary><code>elephant-piggie</code> 학습 단위 25개 (진행 순서)</summary>

- **Elephant & Piggie (출간 순)**
  1. Today I Will Fly!
  2. My Friend Is Sad
  3. I Am Invited to a Party!
  4. There Is a Bird on Your Head!
  5. I Love My New Toy!
  6. I Will Surprise My Friend!
  7. Are You Ready to Play Outside?
  8. Watch Me Throw the Ball!
  9. Elephants Cannot Dance!
  10. Pigs Make Me Sneeze!
  11. I Am Going!
  12. Can I Play Too?
  13. We Are in a Book!
  14. I Broke My Trunk!
  15. Should I Share My Ice Cream?
  16. Happy Pig Day!
  17. Listen to My Trumpet!
  18. Let's Go for a Drive!
  19. A Big Guy Took My Ball!
  20. I'm a Frog!
  21. My New Friend Is So Fun!
  22. Waiting Is Not Easy!
  23. I Will Take a Nap!
  24. I Really Like Slop!
  25. The Thank You Book

</details>

### Epic! (에픽)

*어린이 디지털 도서관 앱* · 비용: 유료 구독 · [공식 사이트](https://www.getepic.com/)

만 12세 이하용 영어 전자책·오디오북·영상 구독 앱. 책이 수만 권이라 '무엇을 읽을지'를 정해 주지 않으면 지금 카드처럼 막연해진다. 책 제목으로 검색해 쓰는 것이 좋다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `epic` | Epic! - Digital Library | 6~7세 | L3 | 앱·활동·읽기 | 10분 | 묶음 | Epic! 앱/웹 → 검색창에 책 제목 입력. 어떤 책을 읽을지는 아직 지정되지 않음 |
| `epic-full` | Epic! - Full Library | 4~7세 | L3 | 앱·활동·읽기 | 10분 | 묶음 | Epic! 앱 전체 — 책이 지정되지 않음 |

### Fly Guy (Tedd Arnold)

*초기 리더스 시리즈* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://www.scholastic.com/)

소년 Buzz와 파리 Fly Guy의 이야기. 짧은 장(chapter)으로 나뉜 초기 리더스이며 첫 권은 'Hi! Fly Guy'.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `flyguy` | Fly Guy series | 6~7세 | L3 | 리더스·그림책·읽기 | 15분 | 묶음 | Fly Guy 시리즈 1권 『Hi! Fly Guy』부터 |

### National Geographic Kids Readers

*논픽션 리더스* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://kids.nationalgeographic.com/)

실제 동물 사진으로 된 논픽션 리더스. Pre-reader → Level 1 → Level 2 순서이며, 관심사가 동물인 아이에게 잘 맞는다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `natgeo-full` | National Geographic Kids - Full Collection | 4~7세 | L3 | 리더스·그림책·읽기 | 15분 | 묶음 | National Geographic Kids Readers 전체 — 권이 지정되지 않음 |
| `natgeo-prereader` | National Geographic Kids - Pre-reader | 6~7세 | L3 | 리더스·그림책·읽기 | 15분 | 묶음 | National Geographic Kids Readers 'Pre-reader' 표시 책 중 아이 관심 동물로 1권 |

### Songbirds Phonics (Julia Donaldson)

*OUP 파닉스 리더스 (Oxford Reading Tree 계열)* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://www.juliadonaldson.co.uk/books/educational/songbird-phonics/)

『The Gruffalo』 작가 Julia Donaldson이 쓴 Oxford Reading Tree 계열 파닉스 리더스 60권. Stage 1+부터 Stage 6까지 단계마다 새로 배우는 소리가 정해져 있어, 배운 소리만으로 읽을 수 있다. ORT 이야기책(Biff·Chip·Kipper)과 함께 많이 쓴다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `songbirds-1` | Songbirds Phonics (ORT) - Stage 1+ | 4~6세 | L3 | 리더스·그림책·읽기 | 15분 | 학습 단위 | Songbirds Stage 1+·More Stage 1+ (12권) — 권 순서는 카드가 매일 안내해요 |
| `songbirds-full` | Songbirds Phonics (ORT) - Full Set | 4~7세 | L3 | 리더스·그림책·읽기 | 15분 | 학습 단위 | 집에 있는 Songbirds 전집을 Stage 1+부터 차례로 (60권) |
| `songbirds-2` | Songbirds Phonics (ORT) - Stage 2-3 | 5~7세 | L4 | 리더스·그림책·읽기 | 15분 | 학습 단위 | Songbirds Stage 2~More Stage 3 (24권) — 권 순서는 카드가 매일 안내해요 |
| `songbirds-3` | Songbirds Phonics (ORT) - Stage 4-6 | 6~7세 | L5 | 리더스·그림책·읽기 | 15분 | 학습 단위 | Songbirds Stage 4~6 (24권) — 권 순서는 카드가 매일 안내해요 |

<details><summary><code>songbirds-1</code> 학습 단위 12개 (진행 순서)</summary>

- **Stage 1+**
  1. Top Cat
  2. Sam's Pot
  3. Bob Bug
  4. Dig, Dig, Dig!
  5. Zak and the Vet
  6. Mum Bug's Bag
- **More Stage 1+**
  7. Cat Naps
  8. Pen Fun
  9. The Big Cod
  10. The Pins and the Pegs
  11. Is It?
  12. Mix, Mix, Mix

</details>

<details><summary><code>songbirds-2</code> 학습 단위 24개 (진행 순서)</summary>

- **Stage 2**
  1. The Odd Pet
  2. Miss! Miss!
  3. This and That
  4. Fish and Chips
  5. Singing Dad
  6. Doctor Duck
- **More Stage 2**
  7. Mr Zed
  8. The Ox and the Yak
  9. The Doll in the Bin
  10. Animal Quiz
  11. The Seven Kids
  12. Ron Rabbit's Egg
- **Stage 3**
  13. The Big Match
  14. The Shopping List
  15. Gran Is Cross
  16. The Trunk and the Skunk
  17. The Scrap Rocket
  18. Splash and Squelch
- **More Stage 3**
  19. Ron Rabbit's Big Day
  20. The Wishing Elf
  21. Bob Bug and the Insect Club
  22. Where Is Snail?
  23. Stop Chatting, Bill
  24. Back to Bed

</details>

<details><summary><code>songbirds-3</code> 학습 단위 24개 (진행 순서)</summary>

- **Stage 4**
  1. Queen Aneena's Feast
  2. Spike Says
  3. The Wrong Kind of Knight
  4. Moan, Moan, Moan!
  5. The Snake and the Drake
  6. Tadpoles
- **More Stage 4**
  7. The Red Man and the Green Man
  8. Pirates
  9. Tails
  10. Pen Pals
  11. My Cat
  12. Tim's Bad Mood
- **Stage 5**
  13. Sue Kangaroo
  14. The Cinderella Play
  15. Usman's Books
  16. The Upside-Down Browns
  17. Leroy
  18. No Milk Today
- **Stage 6**
  19. Tara's Party
  20. Paula the Vet
  21. Where Were You, Bert?
  22. Clare and the Fair
  23. The Deer and the Earwig
  24. Jack and the Giants

</details>

<details><summary><code>songbirds-full</code> 학습 단위 60개 (진행 순서)</summary>

- **Stage 1+**
  1. Top Cat
  2. Sam's Pot
  3. Bob Bug
  4. Dig, Dig, Dig!
  5. Zak and the Vet
  6. Mum Bug's Bag
- **More Stage 1+**
  7. Cat Naps
  8. Pen Fun
  9. The Big Cod
  10. The Pins and the Pegs
  11. Is It?
  12. Mix, Mix, Mix
- **Stage 2**
  13. The Odd Pet
  14. Miss! Miss!
  15. This and That
  16. Fish and Chips
  17. Singing Dad
  18. Doctor Duck
- **More Stage 2**
  19. Mr Zed
  20. The Ox and the Yak
  21. The Doll in the Bin
  22. Animal Quiz
  23. The Seven Kids
  24. Ron Rabbit's Egg
- **Stage 3**
  25. The Big Match
  26. The Shopping List
  27. Gran Is Cross
  28. The Trunk and the Skunk
  29. The Scrap Rocket
  30. Splash and Squelch
- **More Stage 3**
  31. Ron Rabbit's Big Day
  32. The Wishing Elf
  33. Bob Bug and the Insect Club
  34. Where Is Snail?
  35. Stop Chatting, Bill
  36. Back to Bed
- **Stage 4**
  37. Queen Aneena's Feast
  38. Spike Says
  39. The Wrong Kind of Knight
  40. Moan, Moan, Moan!
  41. The Snake and the Drake
  42. Tadpoles
- **More Stage 4**
  43. The Red Man and the Green Man
  44. Pirates
  45. Tails
  46. Pen Pals
  47. My Cat
  48. Tim's Bad Mood
- **Stage 5**
  49. Sue Kangaroo
  50. The Cinderella Play
  51. Usman's Books
  52. The Upside-Down Browns
  53. Leroy
  54. No Milk Today
- **Stage 6**
  55. Tara's Party
  56. Paula the Vet
  57. Where Were You, Bert?
  58. Clare and the Fair
  59. The Deer and the Earwig
  60. Jack and the Giants

</details>

### The Magic School Bus

*과학 애니메이션* · 비용: 스트리밍 서비스 또는 구입 · [공식 사이트](https://www.scholastic.com/)

Ms. Frizzle 선생님과 반 아이들이 마법 버스로 과학 현장을 탐험하는 애니메이션. 첫 에피소드는 'Gets Lost in Space'.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `magicschoolbus` | The Magic School Bus - Episodes | 6~7세 | L3 | 영상·듣기 | 10분 | 묶음 | The Magic School Bus 에피소드 한 편 (1화 'Gets Lost in Space'부터) |

### Amelia Bedelia

*초기 리더스 시리즈* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://www.ameliabedeliabooks.com/)

말을 글자 그대로 알아듣는 가정부 Amelia Bedelia의 이야기. 말장난이 많아 7세 이상에게 맞는다.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `amelia-bedelia` | Amelia Bedelia series | 7~7세 | L4 | 리더스·그림책·읽기 | 15분 | 묶음 | 『Amelia Bedelia』(1963) 첫 권부터 |

### Frog and Toad (Arnold Lobel)

*초기 리더스 (I Can Read)* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://www.icanread.com/)

개구리와 두꺼비의 우정을 다룬 짧은 이야기 모음. 첫 권은 'Frog and Toad Are Friends'.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `frog-and-toad` | Frog and Toad series | 6~7세 | L4 | 리더스·그림책·읽기 | 15분 | 묶음 | 『Frog and Toad Are Friends』부터 |

### Nate the Great

*초기 챕터북 시리즈* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://www.penguinrandomhouse.com/)

꼬마 탐정 Nate가 사건을 푸는 짧은 챕터북. 1권 제목도 'Nate the Great'.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `nate-the-great` | Nate the Great series | 7~7세 | L4 | 리더스·그림책·읽기 | 15분 | 묶음 | Nate the Great 1권 『Nate the Great』부터 |

### Junie B. Jones

*챕터북 시리즈* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://www.penguinrandomhouse.com/)

유치원생 Junie B.의 학교생활 챕터북. 1권은 'Junie B. Jones and the Stupid Smelly Bus'.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `junie-b-jones` | Junie B. Jones series | 7~7세 | L5 | 리더스·그림책·읽기 | 15분 | 묶음 | Junie B. Jones 1권 『Junie B. Jones and the Stupid Smelly Bus』부터 |

### Magic Tree House

*챕터북 시리즈* · 비용: 책 구입 또는 도서관 대출 · [공식 사이트](https://www.magictreehouse.com/)

Jack과 Annie가 마법의 나무집으로 시간 여행을 하는 챕터북. 1권은 'Dinosaurs Before Dark'. 7세 이상 리더스 독해 단계용.

| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |
|---|---|---|---|---|---|---|---|
| `magic-tree-house` | Magic Tree House series | 7~7세 | L5 | 리더스·그림책·읽기 | 15분 | 묶음 | Magic Tree House 1권 『Dinosaurs Before Dark』부터 |

## 학습 단위 카드는 이렇게 나옵니다

같은 자료가 계획에 여러 번 나오면 **1권 첫 읽기 → 1권 다시 읽기 → 2권 첫 읽기 …** 순서로 진도가 나가고,
다음 계획은 이전 계획에서 멈춘 곳부터 이어갑니다. 예) `ort-stage2`의 처음 3일:

1. 『The Big Egg』(Stage 2 First Sentences) 첫 읽기: ① 표지와 그림을 먼저 넘겨 보며 무슨 일이 생길지 한국어로 이야기해요 ② 부모가 글자를 손가락으로 짚으며 한 번 읽어요 ③ 반복되는 문장이 나오면 아이가 따라 읽어요  
   확인 포인트: 그림을 보고 이야기를 예상했나요? 반복 문장을 따라 읽었나요?
2. 『The Big Egg』(Stage 2 First Sentences) 다시 읽기: ① 아이가 기억나는 장면을 먼저 찾아요 ② 함께 읽다가 아이가 아는 단어에서 부모가 멈추고 아이가 읽게 해요 ③ 마음에 든 페이지 하나를 골라 그 문장을 따라 말해요  
   확인 포인트: 어제보다 스스로 읽은 단어가 늘었나요?
3. 『Poor Floppy』(Stage 2 First Sentences) 첫 읽기: ① 표지와 그림을 먼저 넘겨 보며 무슨 일이 생길지 한국어로 이야기해요 ② 부모가 글자를 손가락으로 짚으며 한 번 읽어요 ③ 반복되는 문장이 나오면 아이가 따라 읽어요  
   확인 포인트: 그림을 보고 이야기를 예상했나요? 반복 문장을 따라 읽었나요?

## 출처와 원칙

- 학습 단위 제목 출처 (`oup_ca`): Oxford University Press Canada, Language Arts 주문서 'Oxford Reading Tree — Biff, Chip and Kipper Stories' (https://www.oupcanada.com/school/order_form/a/ORT.Biff.Chip.And.Kipper.Stories.Order.Form.pdf) 의 팩 표지 목록
- 학습 단위 제목 출처 (`jd_site`): Julia Donaldson 공식 사이트 Songbird Phonics 페이지 (https://www.juliadonaldson.co.uk/books/educational/songbird-phonics/) 의 단계별 목록
- 학습 단위 제목 출처 (`jolly_site`): Jolly Learning 공식 사이트 Jolly Phonics 페이지 FAQ 'In what order are the letter sounds taught?' (https://jollylearning.com/en-gb/our-programmes/jolly-phonics) 의 7그룹 순서
- 학습 단위 제목 출처 (`wiki_ep`): Wikipedia 'Elephant & Piggie' 문서의 Books 목록 (https://en.wikipedia.org/wiki/Elephant_and_Piggie) — 출판사(Disney-Hyperion) 페이지는 자동 접속이 막혀 2차 자료로 확인
- 학습 단위 제목 출처 (`wiki_peppa`): Wikipedia 'List of Peppa Pig episodes' 문서의 Series 1 (2004) 방송 순서 (https://en.wikipedia.org/wiki/List_of_Peppa_Pig_episodes) — 에피소드당 약 5분
- 출처(공식 목록 우선, 막힌 경우 명시한 2차 자료)에서 확인한 제목만 학습 단위로 넣습니다. 확인하지 못한 시리즈는 '묶음'으로 남겨 둡니다.
- 저작권(기획서 §7.3): 제목·팩 이름·활동 방법만 다루고 책 본문·영상은 싣거나 호스팅하지 않습니다.

## 남은 일 (묶음 → 학습 단위)

아래 36개는 아직 '앱 전체·시리즈 전체' 단위라 카드가 막연합니다. 공식 목록으로 권·레슨을 확인해 단위로 쪼갤 대상입니다.

`usborne-thatsnotmy`, `khan-kids`, `starfall-abcs`, `abcmouse`, `cocomelon`, `ort-stage1`, `bobbooks-1`, `starfall-read`, `razkids-aa`, `alphablocks`, `scholastic-phonics`, `readingeggs`, `bobbooks-2`, `flyguy`, `natgeo-prereader`, `razkids-bc`, `scholastic-sight`, `magicschoolbus`, `usborne-first`, `starfall-imreading`, `epic`, `sss-library`, `khan-full`, `razkids-full`, `natgeo-full`, `usborne-full`, `epic-full`, `starfall-full`, `abcmouse-full`, `readingeggs-full`, `scholastic-full`, `magic-tree-house`, `nate-the-great`, `junie-b-jones`, `frog-and-toad`, `amelia-bedelia`
