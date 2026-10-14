# ROSA Monitoring Platform Configuration

관련 이슈: https://github.com/neuroplan-hybrid/neuroplan-aws-migration/issues/113

## 1. 목적

ROSA 플랫폼의 모니터링 기반 설정을 보존하고
클러스터 재구축 시 동일한 설정을 재현하기 위한 문서입니다.

Grafana, 애플리케이션 메트릭 수집 및 알림은
모니터링 담당자가 관리합니다.

## 2. 관리 대상

- cluster-monitoring-config.yaml
  - User Workload Monitoring 활성화
  - Namespace: openshift-monitoring
  - enableUserWorkload: true

- thanos-reader-rbac.yaml
  - ServiceAccount: neuroplan/grafana-thanos-reader
  - RoleBinding: openshift-monitoring/grafana-thanos-reader
  - ClusterRole: cluster-monitoring-view

## 3. 적용 및 검증 이력 (2026-10-14)

- ROSA OpenShift 4.20.40
- UWM 활성화 완료
- User Workload Prometheus READY 2/2
- Backend /actuator/prometheus HTTP 200
- Thanos 조회 전용 ServiceAccount 생성 완료
- Thanos 조회용 RBAC 적용 완료
- Thanos API HTTP 200
- PromQL up 조회 성공 (70개 시계열)

## 4. 재구축 절차

1. ROSA 클러스터 및 네임스페이스를 확인합니다.
2. 기존 cluster-monitoring-config 설정을 확인합니다.
3. 기존 설정과 충돌하지 않는지 검토합니다.
4. 승인 후 UWM ConfigMap을 적용합니다.
5. User Workload Prometheus 정상 기동을 확인합니다.
6. 승인 후 Thanos ServiceAccount와 RBAC를 적용합니다.
7. 단기 토큰으로 Thanos API 조회를 검증합니다.
8. Monitoring VM 연결과 운영 토큰 갱신 정책을 확인합니다.

## 5. 운영 주의사항

- 실제 적용 전 반드시 서버 Dry-run을 수행합니다.
- 기존 Monitoring ConfigMap을 임의로 덮어쓰지 않습니다.
- 관리자 kubeconfig 및 인증 토큰을 저장소에 등록하지 않습니다.
- 운영 토큰의 만료 및 갱신 방식은 모니터링 담당자와 협의합니다.
- 이 디렉터리는 현재 Argo CD 자동 적용 대상에 포함되지 않습니다.
- 클러스터 변경은 별도 운영 승인 후 수행합니다.
