# ROSA RDS public CA ConfigMap preparation — issue #93

> **Draft preparation only. Do NOT merge/apply before explicit platform + DB approval.**
> ROSA Argo CD Auto Sync may apply a merged overlay immediately, even when only a ConfigMap is added.
> Current state remains On-Prem Writer / RDS Replica / Route 53 OFF.

## Scope

- GitOps overlay: `overlays/rosa`, namespace `neuroplan`
- Source file: `certs/ap-northeast-2-bundle.pem`, the **public** AWS RDS Seoul Region CA trust bundle (3 root certificates)
- Kustomize `configMapGenerator`: `neuroplan-rds-ca` with key `ca-bundle.pem` and `disableNameSuffixHash: true`
- Exact public CA bundle SHA-256 (verified on the authorized DevOps host, 2026-10-13): `913fb5b814f17af79d4c1622584a8d0ceddf5b0d76fe353d0c7d1186cdd6b229`
- Active RDS CA identifier: `rds-ca-rsa2048-g1` (confirmed via read-only AWS RDS metadata)
- Bundle has `Amazon RDS ap-northeast-2 Root CA RSA2048 G1` plus ECC384/RSA4096 G1 roots
- Official source: https://truststore.pki.rds.amazonaws.com/ap-northeast-2/ap-northeast-2-bundle.pem
- AWS guidance: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html

This PR adds **only a public trust bundle and its ConfigMap generator**. It does NOT modify the Backend Pod, ConfigMap DB_URL, DB credentials, JWT/Gemini Secrets, Route 53, or On-Prem overlay. No CA private key exists in these files. The pinned checksum guards against accidental content changes; before deployment, independently download/recheck the official AWS file as needed.

## Render/check locally (read-only)

```bash
cd ~/neuroplan-gitops
# In the PR branch or an archived copy thereof:
sha256sum overlays/rosa/certs/ap-northeast-2-bundle.pem
grep -c -- '-----BEGIN CERTIFICATE-----' overlays/rosa/certs/ap-northeast-2-bundle.pem
oc kustomize overlays/rosa > /tmp/neuroplan-rosa-ca-rendered.yaml
grep -nE 'name: neuroplan-rds-ca|ca-bundle.pem:' /tmp/neuroplan-rosa-ca-rendered.yaml
```

Expected: SHA-256 `913fb5b814f17af79d4c1622584a8d0ceddf5b0d76fe353d0c7d1186cdd6b229`, exactly 3 `BEGIN CERTIFICATE` entries, successful Kustomize render, and rendered ConfigMap `neuroplan-rds-ca` containing `data.ca-bundle.pem`. Validate only **one** ConfigMap with that name; record rendered YAML evidence without exposing unrelated Secret contents.

## Approval/deployment order

1. Obtain DB owner (정현님) agreement that the public AWS Seoul root CA bundle is the approved trust source; platform confirms management and rotation ownership.
2. Confirm ROSA `neuroplan` namespace and Argo CD application target. **Do not merge** without approval because Auto Sync may create `neuroplan-rds-ca` immediately.
3. After explicit approval, merge **this CA-only PR first** and verify Argo CD Sync/Health and `oc -n neuroplan get configmap neuroplan-rds-ca` with expected data key. No Backend rollout should result from this PR alone; investigate unexpected changes.
4. Reconcile existing Draft PR #14 with latest main (and PR #13 cutover fence stage), then rerender and verify its CA volume mount. **Do not merge #14 until actual JDBC Connector/J verify-full, RDS hostname, authentication, and read-only SQL are proven**, plus DB Writer promotion/app account and Go/No-Go conditions are satisfied.
5. Cutover write-fence (#13), RDS Writer promotion, DB_URL switch (#14), write-unfence, DNS change each need **separate execution approval**. Do not use CA preparation as a Cutover authorization.

## Operational caveats

- An existing RDS instance reports `require_secure_transport=1`; this does **not** prove that real Connector/J TLS/hostname checks have succeeded.
- ConfigMap content is public CA material, **not a Kubernetes Secret**. Never commit database passwords, JWT, TLS private keys, or Kubeconfig.
- Any CA rotation requires a new reviewed GitOps PR and planned Pod renewal/connection verification; `disableNameSuffixHash` intentionally keeps the name stable.
- The expected ConfigMap/PEM key exactly matches PR #14's read-only mount `/etc/neuroplan/rds-ca/ca-bundle.pem`.
