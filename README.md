# NeuroPlan GitOps

**AWS ROSA 운영 환경과 온프레미스 Kubernetes DR 환경의 애플리케이션 배포 설정을 관리하는 저장소입니다.**

애플리케이션 소스와 배포 설정을 분리하고, Kustomize의 `base`와 환경별 `overlays`로 공통 리소스와 환경별 차이를 관리합니다. Jenkins가 Amazon ECR에 저장한 이미지의 태그를 이 저장소에 반영하면, ROSA의 OpenShift GitOps와 온프레미스의 Argo CD가 각 환경의 배포 설정을 동기화합니다.

## 1. 구성 목적

- 애플리케이션 소스 변경 이력과 배포 설정 변경 이력을 분리합니다.
- 공통 Deployment·Service 설정을 재사용하고 환경별 설정을 Overlay로 관리합니다.
- ROSA와 온프레미스 DR에 배포할 서비스별 이미지 버전을 Git으로 관리합니다.
- 배포 변경사항을 커밋 이력으로 추적하고, 각 클러스터의 실제 적용 상태와 대조합니다.

## 2. 저장소 역할

| 저장소 | 관리 범위 |
| --- | --- |
| [neuroplan-application](https://github.com/neuroplan-hybrid/neuroplan-application) | 애플리케이션 소스, Dockerfile, Jenkins CI 파이프라인 |
| **neuroplan-gitops — 현재 저장소** | 공통 Kubernetes 리소스, 환경별 배포 설정, 이미지 태그 |
| [neuroplan-aws-migration](https://github.com/neuroplan-hybrid/neuroplan-aws-migration) | Terraform 인프라, Ansible 구성 자동화, 운영 절차 및 장애 검증 기록 |

## 3. 디렉터리 구성

| 경로 | 주요 내용 |
| --- | --- |
| [`base/10-workloads.yaml`](./base/10-workloads.yaml) | Frontend·Backend Deployment와 Service, Backend ConfigMap, PodDisruptionBudget |
| [`base/kustomization.yaml`](./base/kustomization.yaml) | 공통 리소스 목록 |
| [`overlays/rosa`](./overlays/rosa) | ROSA용 Route, Health Service, TLS RBAC, RDS 연결 및 CA 구성, ServiceMonitor, 이미지 설정 |
| [`overlays/onprem-dr`](./overlays/onprem-dr) | 온프레미스용 HTTPRoute, Backend 설정, 쓰기 차단 및 롤아웃 설정, ECR 인증 참조 |
| [`tests`](./tests) | Backend ServiceMonitor 구성 검증 코드 |
| [`.github/workflows`](./.github/workflows) | ServiceMonitor 구성 검증 Workflow |

## 4. 공통 리소스 구성

`base`는 두 환경이 공유하는 애플리케이션 리소스를 정의합니다.

| 항목 | 설정 |
| --- | --- |
| Frontend·Backend Deployment | 서비스별 Replica 2개 |
| RollingUpdate | `maxUnavailable: 0`, `maxSurge: 1` |
| Pod 분산 | 호스트명 기준 Topology Spread Constraint 적용 |
| PodDisruptionBudget | 서비스별 `minAvailable: 1` |
| 상태 점검 | Frontend Readiness·Liveness, Backend Startup·Readiness·Liveness Probe |
| 컨테이너 보안 | Non-root 실행, 권한 상승 금지, 읽기 전용 루트 파일시스템, Capability 제거 |
| 리소스 관리 | CPU·메모리 requests 및 limits 지정 |
| Backend 종료 처리 | `preStop` 대기와 종료 유예시간 설정 |

PDB는 노드 Drain과 같은 자발적 중단 시 가용 Pod 수를 보호하기 위한 설정입니다. 모든 종류의 장애에서 서비스 무중단을 보장하는 것은 아닙니다.

`base`에는 기존 Harbor 이미지 이름과 인증 Secret 참조가 남아 있으며, 각 Overlay에서 ECR 이미지와 환경별 인증 방식으로 변경합니다. **실제 배포 경로는 `base` 단독이 아닌 환경별 Overlay입니다.**

## 5. 환경별 배포 구성

| 구분 | ROSA | On-Prem DR |
| --- | --- | --- |
| 역할 | 주 운영 환경 | 온프레미스 DR 환경 |
| GitOps 경로 | `overlays/rosa` | `overlays/onprem-dr` |
| Namespace | `neuroplan` | `application` |
| 배포 관리 | OpenShift GitOps | 온프레미스 Argo CD |
| 서비스 진입 | OpenShift Route | Gateway API HTTPRoute |
| 이미지 저장소 | Amazon ECR | Amazon ECR |
| 이미지 인증 | Worker IAM Role 및 ECR Credential Provider | `ecr-pull-secret` |
| Image Pull Policy | `Always` | `IfNotPresent` |
| 사이트 식별값 | `DEPLOYMENT_SITE: rosa` | `DEPLOYMENT_SITE: onprem` |

### ROSA

- `/api` 요청은 Backend Service, `/` 요청은 Frontend Service로 연결합니다.
- Route의 Edge TLS termination과 `externalCertificate` Secret 참조를 사용합니다.
- 라우팅 Health Check용 Service·Route를 별도로 구성합니다.
- RDS 연결에 `sslMode=verify-full`을 사용하고 공개 CA Bundle을 ConfigMap으로 생성해 Backend에 마운트합니다.
- Backend 메트릭 수집을 위한 ServiceMonitor를 포함합니다.

### On-Prem DR

- 기존 `neuroplan-gateway`의 HTTPS Listener에 HTTPRoute를 연결합니다.
- `/api`와 `/` 요청을 각각 Backend와 Frontend로 전달합니다.
- ECR 이미지 Pull에는 별도 준비된 `ecr-pull-secret`을 사용합니다.
- SHA 기반 이미지 태그와 `IfNotPresent` 정책을 사용해 노드에 있는 이미지를 재사용합니다. 캐시가 없는 노드에서 이미지를 받을 때에는 유효한 ECR 인증이 필요합니다.

## 6. CI/CD 연계

1. Jenkins가 Application Repository의 소스를 체크아웃하고 서비스별 변경 여부를 확인합니다.
2. 변경된 서비스의 이미지를 빌드해 Git Commit SHA 기반 태그로 Amazon ECR에 Push합니다. 동일 태그의 이미지가 이미 존재하면 파이프라인 조건에 따라 재사용합니다.
3. ECR 이미지 존재 여부를 검증합니다.
4. 이 저장소를 체크아웃하고, 변경된 서비스의 이미지 태그를 ROSA와 On-Prem DR의 `kustomization.yaml`에 반영합니다.
5. 두 Overlay를 렌더링해 이미지 설정을 확인한 후 변경사항을 Commit·Push합니다.
6. 각 환경의 OpenShift GitOps·Argo CD가 담당 경로의 변경사항을 클러스터에 반영합니다.

Frontend와 Backend의 태그는 각각 관리합니다. 한 서비스만 변경된 경우 다른 서비스의 태그는 유지하며, 같은 서비스의 새 태그를 두 환경의 배포 설정에 함께 반영합니다.

두 클러스터의 동기화는 각각 수행되므로, Git 태그 갱신만으로 양쪽 배포가 동시에 완료되었다고 판단하지 않습니다. 각 환경의 동기화 상태와 실제 Pod 이미지를 확인합니다.

**관련 코드:** [Jenkinsfile.aws](https://github.com/neuroplan-hybrid/neuroplan-application/blob/main/Jenkinsfile.aws) · [ECR 인증 갱신 파이프라인](https://github.com/neuroplan-hybrid/neuroplan-application/blob/main/Jenkinsfile.ecr-secret-refresh)

## 7. 배포 전 준비 사항

- 대상 Namespace와 OpenShift GitOps·Argo CD의 저장소 접근 및 배포 권한을 준비합니다.
- Backend에서 참조하는 `neuroplan-auth-secrets`, `neuroplan-gemini-secrets`를 각 환경에 준비합니다.
- ROSA의 Worker ECR 접근 권한과 Route용 TLS Secret을 준비합니다.
- 온프레미스의 Gateway·HTTPS Listener와 `ecr-pull-secret` 및 인증 갱신 구성을 준비합니다.
- ROSA의 ServiceMonitor를 처리할 CRD와 모니터링 구성을 확인합니다.

인증정보, API Key, 인증서 개인 키는 이 저장소에 저장하지 않습니다. `overlays/rosa/certs`의 RDS CA Bundle은 서버 인증서 검증에 사용하는 공개 신뢰 인증서입니다.

## 8. 설정 렌더링 및 배포 상태 확인

저장소 루트에서 다음 명령으로 각 환경의 최종 매니페스트를 확인할 수 있습니다. 아래 렌더링 명령은 클러스터에 리소스를 적용하지 않습니다.

```bash
kubectl kustomize overlays/rosa > /tmp/neuroplan-rosa.yaml
kubectl kustomize overlays/onprem-dr > /tmp/neuroplan-onprem-dr.yaml
```

Kustomize 렌더링 성공은 매니페스트 조합 확인이며, 클러스터의 CRD·권한·Secret 준비나 실제 배포 성공까지 보장하지 않습니다.

각 클러스터의 Context를 확인한 뒤 실행 상태를 조회합니다.

```bash
# ROSA Context에서 실행
oc -n neuroplan get deploy,pod,svc,route,pdb
oc -n neuroplan get deployment neuroplan-frontend neuroplan-backend \
  -o 'custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[*].image'

# On-Prem Context에서 실행
kubectl -n application get deploy,pod,svc,httproute,pdb
kubectl -n application get deployment neuroplan-frontend neuroplan-backend \
  -o 'custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[*].image'
```

검증 시에는 다음 항목을 함께 확인합니다.

- Jenkins 실행 결과와 ECR 서비스별 이미지 태그
- GitOps 커밋 및 두 환경의 이미지 설정
- 각 Argo CD Application의 `Synced`·`Healthy` 상태
- 실제 Pod의 이미지와 Ready 상태
- 로그인·조회·저장 등 사용자 기능의 정상 동작

## 9. DR 전환 및 변경 관리

환경별 Backend Patch에는 `DEMO_WRITE_FENCE`와 롤아웃을 위한 PodTemplate Annotation이 포함되어 있습니다. ConfigMap 환경변수 변경을 실행 중인 Pod에 반영하기 위해 Deployment 변경을 함께 관리합니다.

현재 구성 파일에는 Failback 기준으로 ROSA 쓰기를 허용하고 온프레미스 쓰기를 차단하는 값이 기록되어 있습니다. 이는 Git에 선언된 설정이며, 실제 운영 상태는 클러스터 및 DB 상태와 함께 확인합니다.

- 쓰기 차단·해제는 DB Writer 전환 및 데이터 정합성 확인 순서에 맞춰 진행합니다.
- ROSA의 `30-backend-config-patch.yaml`과 뒤에 적용되는 `32-backend-rds-url-patch.yaml`에 중복된 쓰기 차단 값이 있으므로 함께 검토합니다.
- Route 53 전환, DB 승격·복제, 데이터 복구는 인프라 저장소의 운영 절차와 연계합니다.
- 이미지 버전 되돌림과 DB·쓰기 차단 설정 되돌림은 영향이 다르므로, 변경 범위를 확인한 후 Git 이력을 활용합니다.

**이 저장소의 동기화는 애플리케이션 배포 설정 반영을 담당하며, DR 전환 전체 절차를 단독으로 수행하지 않습니다.**

## 10. 관련 문서

- [ROSA 초기 배포 준비 기록](./overlays/rosa/README.md)
- [RDS CA GitOps 구성](./overlays/rosa/RDS-CA-GITOPS.md)
- [RDS TLS 사전 점검](./overlays/rosa/RDS-TLS-PREFLIGHT.md)
- [Backend 메트릭 구성](./overlays/rosa/BACKEND-METRICS.md)
- [인프라 운영 절차](https://github.com/neuroplan-hybrid/neuroplan-aws-migration/tree/main/docs/runbooks)
- [팀 장애 검증 결과](https://github.com/neuroplan-hybrid/neuroplan-aws-migration/tree/main/docs/test-results)

초기 준비 문서는 당시 작업 순서를 설명합니다. 현재 배포 대상 리소스와 Patch 적용 순서는 각 Overlay의 `kustomization.yaml`을 기준으로 확인합니다.
