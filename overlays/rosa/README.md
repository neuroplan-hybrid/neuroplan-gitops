# ROSA overlay 준비 및 10/12 적용 순서

## 목적

`overlays/rosa`는 10/12 ROSA HCP 생성 후 NeuroPlan 애플리케이션을 최초 배포하기 위한 P0 경로입니다.

현재 사전 준비 범위:
- 서비스 도메인: `app.neuroplan.cloud`
- Route 53 Primary Health Host: `primary-health.neuroplan.cloud`
- Route 53 Health Check 경로: `/actuator/health/routing`
- Health 전용 Service: `neuroplan-backend-health`
- DB 장애 시에도 Route 53 Health Check가 기존 Backend readiness에 의해 같이 빠지지 않도록 `publishNotReadyAddresses: true`

## Operator / 구성요소 목록

| 우선순위 | 구성요소 | 설치/관리 방식 | 비고 |
|---|---|---|---|
| P0 | Red Hat OpenShift GitOps Operator | ROSA 생성 후 클러스터에 설치 | Argo CD 및 GitOps 첫 배포 선행조건. 실제 ROSA 버전과 호환되는 채널/버전은 10/12에 확인 후 기록 |
| P0 | RDS 애플리케이션 DB 인증 | Kubernetes Secret 기반 정적 DB 계정 | RDS Writer 전환 후 ROSA Backend 전환 전에 RDS 전용 정적 DB 계정과 Kubernetes Secret 준비. 비밀번호는 Git에 저장하지 않음 |

추가 Ingress/Gateway Operator는 P0에 넣지 않습니다. ROSA 애플리케이션 진입은 기본 OpenShift Route/IngressController를 사용합니다.

cert-manager도 P0에 설치하지 않습니다. #34 결정대로 DNS-01 인증서는 Infra VM에서 별도 발급하고, 인증서/개인 키는 Git에 커밋하지 않습니다.

## 10/12 ROSA 생성 후 P0 적용 순서

1. 클러스터/Worker 상태 확인
   - OpenShift 실제 버전
   - Worker 3대 Ready
   - IAM / STS / OIDC
   - 기본 IngressController 상태
2. Red Hat OpenShift GitOps Operator 설치 및 실제 설치 버전 기록
3. Argo CD 준비 후 이 저장소의 `overlays/rosa`를 첫 애플리케이션 경로로 연결
4. 애플리케이션 Secret은 클러스터에 별도 생성
   - 인증/LLM/DB 관련 Secret 값은 Git에 저장하지 않음
5. ECR 이미지 Pull 확인
6. Frontend / Backend / Service / Route 상태 확인
7. `neuroplan-backend-health`의 Endpoint가 Backend Pod를 포함하는지 확인
8. Backend 이미지에 `routing` Health Group이 반영된 후 `/actuator/health/routing` 확인

## TLS 처리

현재 Route는 `edge` termination과 실제 Host를 사전 정의합니다.

사용자 인증서 연결은 실제 ROSA/OpenShift 버전에서 Route의 Secret 참조 방식 지원 여부를 확인한 뒤 별도 반영합니다.

- ROSA용 인증서 SAN: `app.neuroplan.cloud`, `primary-health.neuroplan.cloud`
- 인증서/개인 키/Secret 데이터는 Git에 저장하지 않음
- 기본 IngressController의 `defaultCertificate`는 교체하지 않음
- Route 단위 TLS 원칙 유지

## Health Check 기준

- Route 53: `https://primary-health.neuroplan.cloud/actuator/health/routing`
  - Backend Health Group: `livenessState,deploymentSafety`
  - DB 제외
- Kubernetes readiness: `/actuator/health/readiness`
  - DB 포함
- Kubernetes liveness: `/actuator/health/liveness`
  - DB 제외

`neuroplan-backend-health`는 기존 `neuroplan-backend`와 동일한 selector를 사용하지만 `publishNotReadyAddresses: true`로 구성합니다.

따라서 DB 장애로 기존 Backend Pod가 NotReady가 되어 일반 `neuroplan-backend` Service에서 제외되더라도, Route 53용 Health 경로는 DB 상태와 분리해서 관측할 수 있습니다.

## 검증 명령 예시

```bash
oc -n neuroplan get deploy,pod,svc
oc -n neuroplan get svc neuroplan-backend-health -o yaml
oc -n neuroplan get route neuroplan-api neuroplan-frontend neuroplan-primary-health
oc -n neuroplan get endpointslice -l kubernetes.io/service-name=neuroplan-backend-health
```

DNS/TLS/Backend routing group까지 준비된 이후:

```bash
curl -i https://primary-health.neuroplan.cloud/actuator/health/routing
```

정상 기대값은 HTTP 200입니다.

## RDS 전환 및 Vault 제외 결정

- 10/12 최초 ROSA 배포는 기존 On-Prem MaxScale DB 연결을 유지합니다.
- RDS Writer 전환 완료 후, ROSA Backend의 DB_URL·Secret을 RDS로 전환하기 전에 RDS 전용 정적 DB 계정과 Kubernetes Secret을 준비합니다.
- DB_URL은 실제 RDS Endpoint 확인 후 별도 RDS Overlay에서 변경합니다.
- Vault Server, VSO 및 동적 DB 계정은 이번 구축·시연 범위에서 제외합니다.
- 기존 Vault 전용 GitOps 코드는 별도 PR에서 제거하며, 필요한 경우 Git 이력을 통해 확인할 수 있습니다. Vault Server 및 VSO는 배포하지 않습니다.
- DB 계정과 비밀번호는 Git에 저장하지 않습니다.
