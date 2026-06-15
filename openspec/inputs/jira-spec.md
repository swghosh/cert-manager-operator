# RFE-5620: Cert-Manager Performance Tuning for High-Volume Environments

## Nature and Description

Cert-manager needs performance tuning in bigger environments where there are hundreds of certificates issued. There are some corner cases like Disaster Recovery in which cert-manager needs to issue a high number of certificates at once.

The following parameters will be exposed via CertManager CR fields:
- `--max-concurrent-challenges`
- `--concurrent-workers`
- `--kube-api-qps`
- `--kube-api-burst`

## Scope

- **In scope:** Expose the four parameters listed above via CertManager CR fields
- **Out of scope:** Additional parameter research/evaluation

## API Design

Parameters will be exposed as fields on the CertManager Custom Resource.

## Defaults

Default values come from upstream cert-manager: https://cert-manager.io/docs/cli/controller/

## Platform Applicability

Platform independent - applies to all supported platforms (OpenShift, MicroShift, Hypershift).

## User Persona

Same as RBAC provided to CertManager CR (cluster admin with permissions to modify CertManager CR).

## Acceptance Criteria

1. Existing e2e tests must pass with the new parameters
2. Parameters are correctly propagated to cert-manager controller deployment
3. (Optional/Future) Performance e2e tests with high certificate volume - not required immediately

## Business Justification

Speed up the certificate issue process in case of rapid renew/creation of certificates.

## Affected Components

- cert-manager-operator (CertManager CR API, controller logic)
