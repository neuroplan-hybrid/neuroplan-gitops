# #93 / PR #14 — ROSA → RDS JDBC TLS preflight (DRAFT)

> **No action in this document is approved for immediate execution.**
> Current operation: On-Prem Writer / RDS Replica / Route 53 OFF.
> The GitOps PR remains Draft until DB + platform agree on the CA trust policy and a
> real JDBC connection from ROSA is verified. Do not merge or execute Cutover early.

## Chosen proposal (pending DB review)

- Running Backend image `e5d288f` uses Java 21 and MariaDB Connector/J `3.5.7`.
- Require `sslMode=verify-full` (TLS encryption, CA chain verification, RDS hostname verification).
- JDBC URL also specifies `serverSslCert=/etc/neuroplan/rds-ca/ca-bundle.pem`.
- The ROSA Backend Deployment mounts **public CA certificates**, not passwords, from
  ConfigMap `neuroplan-rds-ca` key `ca-bundle.pem`, as read-only.
- Do **not** use `sslMode=disable`, `sslMode=trust`, or disable hostname verification
  as an unchecked fallback.
- The ConfigMap is an **external precondition** of this Draft PR, not yet created by
  this PR. Missing ConfigMap/key deliberately prevents Pods from becoming ready.
  Installing the bundle requires separate change approval.
- The selected RDS instance's `CACertificateIdentifier`, RDS parameter group TLS
  requirements, and actual cert chain **have not been verified in this PR**.

MariaDB Connector/J guide: https://mariadb.com/docs/connectors/mariadb-connector-j/using-tls-ssl-with-mariadb-java-connector

AWS RDS trust certificates:
https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html

AWS Seoul Region official public bundle:
https://truststore.pki.rds.amazonaws.com/ap-northeast-2/ap-northeast-2-bundle.pem

## Before merge: check and provision CA trust (separate approval required)

1. **Read-only** instance metadata check on an authorized AWS CLI host:
   ```bash
   aws rds describe-db-instances --region ap-northeast-2 \
     --db-instance-identifier neuroplan-rds-operation \
     --query 'DBInstances[0].[CACertificateIdentifier,DBParameterGroups[0].DBParameterGroupName]' \
     --output table
   ```
2. Download **public** Seoul-region RDS CA bundle from the official AWS HTTPS endpoint
   on the approved DevOps host. Check certificate subjects, issuers and SHA-256:
   ```bash
   curl --fail --silent --show-error --location \
     https://truststore.pki.rds.amazonaws.com/ap-northeast-2/ap-northeast-2-bundle.pem \
     --output /tmp/ap-northeast-2-bundle.pem
   grep -c -- '-----BEGIN CERTIFICATE-----' /tmp/ap-northeast-2-bundle.pem
   sha256sum /tmp/ap-northeast-2-bundle.pem
   keytool -printcert -file /tmp/ap-northeast-2-bundle.pem
   ```
   Review that the **RDS root CA** identified by the instance is present in the
   official bundle. AWS recommends trusting root CA(s), not intermediate certs.
3. After explicit approval, provision `neuroplan-rds-ca` with key
   `ca-bundle.pem` in ROSA namespace `neuroplan`, preferably through a separate
   reviewed GitOps-managed ConfigMap. **Do not create or modify it automatically
   just because this document exists.** If provisioned outside GitOps, document
   ownership and reconciliation before merging this PR.
4. Confirm that both copies of the trust bundle are valid, and that the
   `neuroplan-rds-ca` key is present without dumping private Secrets.
5. Confirm on RDS that TLS is supported/required as agreed. Validate a **real
   MariaDB Connector/J TLS connection from the ROSA network**, including trusted
   CA, hostname match, account permissions, and read-only SQL/health checks at the
   approved point in the Cutover procedure. Never report this as tested until
   evidence exists. A raw TCP/3306 check is **not** JDBC/TLS validation.
6. `oc kustomize overlays/rosa` or `kubectl kustomize overlays/rosa`
   (read-only manifest rendering): verify that the rendered Backend still retains
   its existing `/tmp` mount, Secret `envFrom` entries, routing/health checks,
   and the new public CA volume/mount. After PR #13 is merged, repeat with the
   updated `main` branch base and check for patch conflicts.
7. Confirm that after applying the approved changes, new Backend Pods are Ready,
   old Pods terminated, TLS/JDBC and read-only DB queries succeed.
   Keep `DEMO_WRITE_FENCE=true` until a *separate* explicit write-resume approval.

## Fence release / Kustomize patch order

After PR #13, `30-backend-config-patch.yaml` configures a write fence;
this PR's later `32-backend-rds-url-patch.yaml` also has
`DEMO_WRITE_FENCE: "true"`. **Setting 30 to false alone is NOT enough.**
The later 32 patch wins. A separate reviewed PR must remove or set **the later
32 patch** key to false, update the Backend PodTemplate annotation (or other
approved rollout trigger), then re-check all Pods and DB Writer identity.
Do not enable an On-Prem Writer by accident.

## Other Cutover blockers

- On-Prem DB hosts → RDS:3306 connectivity for reverse replication currently
  reported as failing; network owner must resolve/verify before Cutover.
- #13 backend write-fence rollouts and DB-side no-write checks must complete
  before promoting RDS.
- RDS application account/CRUD rights and authentication must be validated by DB
  owner *after* Writer promotion, before this PR is applied.
- Preserve JWT/Gemini secrets; store no DB passwords or private TLS keys in Git.
- **Route 53 OFF** until separately approved.

This is an **implementation proposal**, not proof of TLS connectivity or
production readiness.
