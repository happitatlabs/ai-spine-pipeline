# Spine CLI Export Setup

## 목적

`Spine.com`을 절대경로로 호출해서 `.spine` 프로젝트를 PowerShell에서 자동 export한다.

현재 기준으로 검증한 범위는 다음과 같다.

- `.spine` 입력 파일 지정
- 출력 폴더 자동 생성
- `json+pack` export 수행
- 결과물 `.json`, `.atlas`, `.png` 생성 확인

## 현재 세팅값

- Spine CLI 경로: `C:\Program Files\Spine\Spine.com`
- 작업 루트: `D:\Spine`
- 프로젝트 입력 루트: `D:\Spine\projects`
- export 출력 루트: `D:\Spine\export`
- export 스크립트: [spine_export.ps1](D:\Spine\spine_export.ps1)
- Git 저장소: `D:\Spine\.git`

## 디렉토리 구조

```text
D:\Spine
  README.md
  spine_export.ps1
  projects\
  export\
  vendor\
```

현재 확보한 공식 예제는 아래 경로에 있다.

- 원본 예제 저장소 일부: `D:\Spine\vendor\spine-runtimes`
- 테스트용 복사본: `D:\Spine\projects\spineboy\spineboy-ess.spine`

## Git 기준 운영

현재 `D:\Spine`은 Git 저장소로 초기화되어 있다.

```powershell
git -C "D:\Spine" status
```

기본 추적 대상:

- `README.md`
- `spine_export.ps1`
- `.gitignore`
- 빈 디렉토리 유지용 `.gitkeep`

기본 제외 대상:

- `export/`
- `vendor/`
- `projects/`

이렇게 둔 이유:

- `export/`는 생성 산출물이므로 버전 관리 대상이 아님
- `vendor/`는 공식 예제/외부 소스 복사본이므로 기본 제외
- `projects/`는 실제 작업용 `.spine` 자산이 들어갈 가능성이 높아 기본적으로 로컬 관리

나중에 실제 `.spine` 프로젝트 자체를 Git에 올리고 싶으면 `.gitignore`에서 `projects/` 관련 규칙을 조정하면 된다.

초기 업로드 예시는 아래처럼 진행하면 된다.

```powershell
git -C "D:\Spine" add README.md spine_export.ps1 .gitignore projects/.gitkeep export/.gitkeep
git -C "D:\Spine" commit -m "Add Spine CLI export automation setup"
```

### safe.directory 메모

이 환경에서는 `D:\Spine` 저장소가 현재 Windows 사용자와 다른 소유자로 보일 수 있어서 Git이 `dubious ownership` 오류를 낼 수 있다.

그 경우 아래 설정으로 이 저장소만 신뢰 대상으로 추가하면 된다.

```powershell
git config --global --add safe.directory D:/Spine
```

현재 반영 상태는 아래 명령으로 확인할 수 있다.

```powershell
git config --global --get-all safe.directory
```

## 기본 사용법

```powershell
& "D:\Spine\spine_export.ps1" `
  -InputPath "D:\Spine\projects\spineboy\spineboy-ess.spine" `
  -OutputPath "D:\Spine\export\spineboy-ess"
```

기본 export 모드는 `json+pack`이다.

- `json+pack`: `.json`, `.atlas`, `.png`
- `json`: `.json`
- `binary+pack`: `.skel`, `.atlas`, `.png`
- `binary`: `.skel`

모드를 바꾸려면 `-ExportMode`를 명시한다.

```powershell
& "D:\Spine\spine_export.ps1" `
  -InputPath "D:\Spine\projects\spineboy\spineboy-ess.spine" `
  -OutputPath "D:\Spine\export\spineboy-json-only" `
  -ExportMode "json"
```

## 실제 검증 결과

다음 명령으로 실제 export를 확인했다.

```powershell
& "D:\Spine\spine_export.ps1" `
  -InputPath "D:\Spine\projects\spineboy\spineboy-ess.spine" `
  -OutputPath "D:\Spine\export\spineboy-ess"
```

생성 결과:

```text
D:\Spine\export\spineboy-ess\
  spineboy-ess.json
  spineboy-ess.atlas
  spineboy-ess.png
```

## 알아야 하는 것

### 1. PATH 등록에 의존하지 않는다

`Spine.com`은 PATH에 없으므로 항상 절대경로로 호출한다.

```powershell
& "C:\Program Files\Spine\Spine.com" ...
```

### 2. `-u`는 headless 옵션이 아니다

처음 가정과 달리 `-u`는 `update` 옵션이다. export 실행에는 쓰지 않는다.

- 잘못된 이해: `-u = UI 없이 실행`
- 실제 의미: `-u = 특정 Spine 버전 업데이트/선택`

export에는 보통 아래 조합을 사용한다.

```powershell
& "C:\Program Files\Spine\Spine.com" `
  -i "<input.spine>" `
  -o "<output-folder>" `
  -e "json+pack"
```

### 3. `.atlas`와 `.png`까지 원하면 `json`만으로는 부족하다

`-e json`은 JSON 데이터 export만 의미한다.

`.atlas`와 `.png`까지 같이 만들려면 `-e json+pack`을 사용해야 한다.

### 4. 자동화할 때는 같은 프로젝트를 열어둔 Spine 창을 닫는 쪽이 안전하다

필수는 아니지만 아래 이유로 닫고 실행하는 것을 권장한다.

- 같은 `.spine` 파일을 GUI에서 열어 둔 상태와 충돌 가능성
- 미저장 변경 반영 여부 혼선
- 배치 작업 시 재현성 저하

권장 운영 기준:

- 수동 테스트: 열려 있어도 될 수 있음
- 배치/자동화: 닫고 실행 권장
- 같은 프로젝트 편집 중: 저장 후 닫고 실행 권장

### 5. Spine CLI도 실행 환경 영향을 받는다

이번 검증에서 일반 실행은 성공했지만, 제한된 실행 환경에서는 `Spine.com`이 비정상 종료할 수 있었다.

가능한 원인:

- OpenGL/윈도우 시스템 접근 제한
- 자동화 도구의 샌드박스 제한

따라서 실제 운영 자동화는 일반 PowerShell 또는 충분한 권한이 있는 실행 환경에서 돌리는 것이 안전하다.

### 6. 버전 매칭이 중요하다

Spine editor의 major/minor 버전과 runtime 쪽 major/minor 버전은 맞춰야 한다.

예:

- editor `4.2.x` -> runtime도 `4.2`
- editor `4.3.x` -> runtime도 `4.3`

현재 확인된 실행 버전:

- Launcher: `4.3.02`
- 실행된 Editor: `4.2.43 Professional`

## 문제가 생기면 먼저 볼 것

### 입력 파일 없음

오류 예:

```text
Input .spine file not found: ...
```

확인:

- 경로 오타
- `.spine` 확장자 여부

### export는 끝났는데 결과물 일부가 없음

확인:

- `-ExportMode`가 `json+pack` 또는 `binary+pack`인지
- 출력 폴더를 잘못 보지 않았는지

### Spine 자체가 종료 코드와 함께 죽음

확인:

- Spine 창을 닫고 재시도
- 일반 PowerShell에서 재시도
- `C:\Users\Hyein\Spine\spine.log` 확인

## 다음 확장 후보

- `D:\Spine\projects` 전체 순회 일괄 export
- 프로젝트별 출력 폴더 자동 매핑
- 로그 파일 저장
- CI/빌드 파이프라인 연결

## STEP 1 구현 상태

현재 저장소에는 STEP 1 기준의 최소 파이프라인 구현이 추가되어 있다.

- 엔트리포인트: [pipeline/step1.py](D:\Spine\pipeline\step1.py)
- 템플릿: [bone_template.yaml](D:\Spine\spine\templates\humanoid_v1\bone_template.yaml)
- 기준 JSON: [template_export.json](D:\Spine\spine\templates\humanoid_v1\template_export.json)
- 샘플 manifest: [humanoid_a](D:\Spine\samples\parts\humanoid_a\parts_manifest.json), [humanoid_b](D:\Spine\samples\parts\humanoid_b\parts_manifest.json), [humanoid_c](D:\Spine\samples\parts\humanoid_c\parts_manifest.json)

핵심 동작:

- `parts_manifest.json` 로드
- `anchor_hint -> category+side fallback` 규칙 기반 매핑
- `spine_import_bundle/` 생성
- `draft_skeleton.json`, `bundle_meta.json`, `slot_map.json`, `review_report.json` 생성
- 1차 roundtrip: `template patch -> Spine CLI export(json+pack)`
- 선택 2차 roundtrip: `JSON import -> clean -> export(json+pack)`

### draft_skeleton 최소 구조

현재 구현은 최소한 아래 top-level 키를 보장한다.

```json
{
  "bones": [...],
  "slots": [...],
  "skins": [...]
}
```

참고:

- 로더/패처는 `skins`가 리스트인 Spine export JSON과 객체형 최소 구조를 둘 다 처리한다.
- 실제 템플릿 파일은 현재 Spine 예제 export JSON과의 호환을 위해 리스트형 `skins`를 사용한다.

### STEP 1 실행 예시

```powershell
python -m pipeline.step1 `
  --parts-manifest "D:\Spine\samples\parts\humanoid_a\parts_manifest.json" `
  --template-id "humanoid_v1" `
  --bundle-dir "D:\Spine\artifacts\humanoid_a\bundle" `
  --roundtrip-dir "D:\Spine\artifacts\humanoid_a\roundtrip" `
  --force
```

2차 roundtrip까지 같이 보려면:

```powershell
python -m pipeline.step1 `
  --parts-manifest "D:\Spine\samples\parts\humanoid_a\parts_manifest.json" `
  --template-id "humanoid_v1" `
  --bundle-dir "D:\Spine\artifacts\humanoid_a\bundle" `
  --roundtrip-dir "D:\Spine\artifacts\humanoid_a\roundtrip" `
  --run-secondary-roundtrip `
  --secondary-project-path "D:\Spine\artifacts\humanoid_a\roundtrip\generated.spine" `
  --force
```

### 테스트

로컬 단위 테스트:

```powershell
pytest -q
```

현재 테스트 범위:

- anchor 기반 매핑
- category/side fallback 매핑
- bundle 최소 구조 생성
- fake CLI 기반 workflow PASS 리포트 생성

### STEP 1 결과 요약

- STEP 1은 `분리된 파츠 이미지 + humanoid_v1 템플릿 -> draft_skeleton.json 생성 -> Spine CLI roundtrip 검증` 범위까지 구현 및 로컬 검증 완료
- 로컬 검증 결과: `pytest -q: 4 passed`, primary roundtrip `3/3 PASS`, secondary roundtrip `1건 PASS`
- 샘플 실행 시간: 약 `4.2s / 4.2s / 4.3s`, unresolved mapping은 전부 `0`
- `humanoid_b`는 fallback 경로 검증용 샘플이며 `mapping_confidence_avg=0.7917`로 기록됨
- 현재 완료 범위는 `단일 템플릿(humanoid_v1)`과 `샘플 3세트` 기준의 로컬 검증
- 아직 포함되지 않은 범위는 `원화 자동 분리`, `텍스트 기반 생성`, `다중 템플릿 일반화`, `정량 layout metric`
- 현재 산출물은 사람이 Spine에서 후처리할 수 있는 리깅 초안이며, 완전 자동 리깅 결과물을 의미하지 않는다

## STEP 2 구현 상태

현재 저장소에는 STEP 2 기준의 deterministic pre-rig normalization layer가 추가되어 있다.

- 엔트리포인트: [pipeline/step2.py](D:\Spine\pipeline\step2.py)
- 스캐너: [asset_scanner.py](D:\Spine\pipeline\asset_scanner.py)
- 정규화기: [normalizer.py](D:\Spine\pipeline\normalizer.py)
- 검수 리포트: [review.py](D:\Spine\pipeline\review.py)
- 계약 정의: [step2_contracts.py](D:\Spine\pipeline\step2_contracts.py)
- 템플릿 규칙: [bone_template.yaml](D:\Spine\spine\templates\humanoid_v1\bone_template.yaml)
- 샘플 입력: [normal_case](D:\Spine\samples\step2\normal_case), [fallback_case](D:\Spine\samples\step2\fallback_case), [ambiguous_case](D:\Spine\samples\step2\ambiguous_case)

핵심 동작:

- 입력 디렉토리의 PNG 자산 재귀 스캔
- 파일명/경로 tokenization 및 structured trace 기록
- category / side / variant token scoring 기반 추론
- deterministic duplicate arbitration
- `normalized_manifest.json`, `step1_parts_manifest.json`, `review_report.json` 생성
- `normalized_assets/selected`, `normalized_assets/rejected` 분리 복사
- 상태에 따라 STEP 1 호출 또는 차단

### STEP 2 출력 구조

```text
step2_output/
  normalized_manifest.json
  step1_parts_manifest.json
  review_report.json
  normalized_assets/
    selected/
    rejected/
```

`normalized_manifest.json`에는 scanner 결과와 normalization 결과가 같이 담긴다.

각 part 항목 최소 필드:

- `source_path`
- `normalized_name`
- `category`
- `side`
- `variant`
- `anchor_hint`
- `bbox`
- `pivot_hint`
- `confidence`
- `selected`
- `trace`

`review_report.json`에는 아래 항목이 포함된다.

- `status`
- `summary`
- `issues`
- `low_confidence_parts`
- `unresolved_parts`
- `duplicate_groups`
- `missing_required_parts`
- `notes`
- `step1_status`
- `step1_error`

### STEP 2 실행 예시

STEP 2만 실행:

```powershell
python -m pipeline.step2 `
  --input-dir "D:\Spine\samples\step2\fallback_case" `
  --template-id "humanoid_v1" `
  --output-dir "D:\Spine\artifacts\step2\fallback_case" `
  --force
```

STEP 2 후 STEP 1까지 연결:

```powershell
python -m pipeline.step2 `
  --input-dir "D:\Spine\samples\step2\normal_case" `
  --template-id "humanoid_v1" `
  --output-dir "D:\Spine\artifacts\step2\normal_case" `
  --run-step1 `
  --force
```

### STEP 2 상태 규칙

- `PASS`: required canonical part 충족, duplicate 없음, unresolved 없음, low confidence 없음
- `REVIEW_REQUIRED`: selected set은 만들 수 있지만 검수 경고가 남아 있음
- `FAIL`: required canonical set을 만들 수 없음

STEP 1 호출 규칙:

- `FAIL`이면 STEP 1 호출 금지
- `REVIEW_REQUIRED`이면 `--force-step1`일 때만 STEP 1 실행
- `PASS`이면 `--run-step1`일 때 STEP 1 실행

STEP 1 실행 요청 후 결과 해석 규칙:

- `--run-step1` 또는 `--force-step1`가 지정되면 STEP 1은 `requested` 상태로 간주한다
- `requested` 상태에서는 `step1_status=PASS`만 성공이다
- `requested` 상태에서 `step1_status=SKIPPED`, `FAIL`, `ERROR`는 모두 STEP 2 CLI 실패로 간주한다
- `NOT_REQUESTED`는 STEP 1 실행이 요청되지 않은 경우에만 중립 상태다

### STEP 2 검증 결과

- `pytest -q`: `10 passed`
- `normal_case`: `PASS`, `step1_status=PASS`
- `fallback_case`: `REVIEW_REQUIRED`, `step1_status=SKIPPED`
- `ambiguous_case`: `FAIL`

현재 범위에서 확인된 사실:

- STEP 2는 입력 자산 편차를 deterministic rule-based 방식으로 정규화한다
- STEP 2 결과는 현재 STEP 1 입력 계약으로 바로 연결된다
- duplicate, unresolved, low-confidence, missing-required-part가 review report에 구조적으로 기록된다

아직 포함되지 않은 범위:

- 딥러닝 기반 자동 분할
- 텍스트 기반 이미지 생성
- Spine Editor bone/keyframe/timeline 직접 편집
- 다중 템플릿 일반화
- 정량 layout metric 자동 판정
