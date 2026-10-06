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
| P1 | HashiCorp Vault Server | `bootstrap/rosa-vault`의 Argo CD Helm Application | P0 RDS 전환/DR 검증을 막지 않는 별도 PoC |
| P1 | HashiCorp Vault Secrets Operator | `bootstrap/rosa-vault`의 Argo CD Helm Application | 현재 저장소 기준 chart `1.6.0`; Cutover 후 ROSA Backend → RDS 동적 자격증명 경로에서 사용 |

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

## P1 Vault 경로

Vault는 P0 첫 배포와 분리합니다.

- Bootstrap: `bootstrap/rosa-vault`
- 애플리케이션 Overlay: `overlays/rosa-vault`
- 목표: Cutover 후 ROSA Backend → RDS 운영 경로에 동적 DB 자격증명 적용
- P0 RDS 전환 및 DR 검증이 우선이며, Vault/VSO 문제로 P0 일정이 차단되면 안 됨
