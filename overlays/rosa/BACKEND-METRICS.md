# ROSA Backend metrics collection

## Scope
The ROSA overlay adds one ServiceMonitor in neuroplan. It selects the existing neuroplan-backend Service by app.kubernetes.io/name, scrapes its named http port (8080) at /actuator/prometheus every 30 seconds, and times out after 10 seconds. Namespace selection is omitted intentionally: only Services in the monitor's own namespace are considered.

No Deployment, Service, DB URL, JWT Secret, write fence, CA, Route, image tag, Thanos reader RBAC, UWM ConfigMap, or onprem-dr resource is changed. This uses the already-enabled ROSA User Workload Monitoring stack; no new Prometheus or Grafana server is installed.

This PR does not add PrometheusRule, email routing, or a dashboard. It does not include a token. The HTTP endpoint is internal Service traffic, not the external Thanos HTTPS connection.

## Evidence and prerequisites
- Platform reported UWM ready and Backend /actuator/prometheus HTTP 200.
- Actual user output: no ServiceMonitor in neuroplan.
- Actual user output: Service metadata label app.kubernetes.io/name=neuroplan-backend; port http=8080; targetPort=http.
- Grafana ROSA Thanos Save & test, up, and neuroplan Pod readiness succeed.
- http_server_requests_seconds_count is currently absent from the reader's Grafana queries. Successful scraping and reader access must both be verified after deployment.
- Confirm neuroplan is not excluded from user-workload monitoring and UWM can connect to the Service. Do not label it for default openshift cluster monitoring.
- ServiceMonitor CRD and Argo CD permission for monitoring.coreos.com/ServiceMonitor must exist.

## Review, merge, and deployment
Review and agree the deployment window with the platform owner before merging. This file IS included in overlays/rosa, so merge may trigger Argo CD Auto-Sync and a real ROSA resource creation. Coordinate with T1/T2/T4/T5. Do not manually oc apply this file outside the agreed GitOps procedure.

CI renders baseline and changed ROSA/onprem-dr overlays. It checks that ROSA gains only this monitor, all existing objects are identical, onprem-dr is identical, and the Service label/port match. These checks do not prove cluster admission, target reachability, or actual scraping.

## Post-Sync read-only checks
Run on DevOps VM as devops using the ROSA-specific kubeconfig:

```bash
oc --kubeconfig=/home/devops/.kube/config-rosa-neuroplan -n neuroplan get servicemonitor neuroplan-backend -o yaml
oc --kubeconfig=/home/devops/.kube/config-rosa-neuroplan -n neuroplan get endpointslice -l kubernetes.io/service-name=neuroplan-backend
```

Verify Argo CD Synced/Healthy and check the user-workload Prometheus target in the OpenShift monitoring interface. After several scrape intervals, query these in Grafana ROSA Thanos:

```promql
up{namespace="neuroplan",service="neuroplan-backend"}
```

```promql
http_server_requests_seconds_count{namespace="neuroplan"}
```

```promql
sum(rate(http_server_requests_seconds_count{namespace="neuroplan",uri!~"/actuator.*"}[5m]))
```

```promql
histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{namespace="neuroplan",uri!~"/actuator.*"}[5m])))
```

Do not turn absent data into zero requests or a healthy status. If target is absent: check UWM exclusion/selectors/CRD/Argo permission. If target is DOWN: check endpoint reachability and scrape error. If target is UP but Grafana lacks metrics: inspect actual metric labels and user-workload reader permissions. Do not broaden RBAC without review.

For request-rate/latency validation, use approved normal app requests. Do not create DB writes, disable a fence, inject failures, or change Route 53 solely for this verification. HTTP counters may include health/scrape traffic. The actuator exclusion above is only for application panels, not for changing collection.

## Rollback
Remove this resource reference and ServiceMonitor through a reviewed GitOps change. This stops collection without changing Backend traffic or DB settings.

## Reference
https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/monitoring_apis/servicemonitor-monitoring-coreos-com-v1
