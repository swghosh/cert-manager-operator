# Feature Specification: Cert-Manager Performance Tuning Parameters

**Feature Branch**: `rfe-5620-cert-manager-performance-tuning`

**Created**: 2026-06-11

**Status**: Draft

**Input**: RFE-5620 - Enable performance tuning for cert-manager in high-volume environments

## User Scenarios & Testing

### User Story 1 - Configure Concurrent Workers (Priority: P1)

As a cluster administrator, I want to configure the number of concurrent workers for cert-manager controller so that I can increase certificate issuance throughput in large environments.

**Why this priority**: This is the primary mechanism for controlling parallel certificate processing. Higher worker count directly impacts issuance speed.

**Independent Test**: Can be tested by setting the concurrent-workers parameter and verifying the controller deployment reflects the configuration.

**Acceptance Scenarios**:

1. **Given** a CertManager CR with concurrent-workers set to 4, **When** the operator reconciles, **Then** the cert-manager controller deployment has the `--concurrent-workers=4` argument.
2. **Given** a CertManager CR without concurrent-workers specified, **When** the operator reconciles, **Then** the cert-manager controller uses the upstream default value.

---

### User Story 2 - Configure Max Concurrent Challenges (Priority: P1)

As a cluster administrator, I want to configure the maximum number of concurrent ACME challenges so that I can speed up certificate issuance during disaster recovery scenarios where many certificates need renewal simultaneously.

**Why this priority**: Critical for DR scenarios where hundreds of certificates may need issuance at once. ACME challenge bottleneck is a common performance issue.

**Independent Test**: Can be tested by setting the max-concurrent-challenges parameter and verifying the controller deployment reflects the configuration.

**Acceptance Scenarios**:

1. **Given** a CertManager CR with max-concurrent-challenges set to 120, **When** the operator reconciles, **Then** the cert-manager controller deployment has the `--max-concurrent-challenges=120` argument.
2. **Given** a CertManager CR without max-concurrent-challenges specified, **When** the operator reconciles, **Then** the cert-manager controller uses the upstream default value.

---

### User Story 3 - Configure Kubernetes API Rate Limits (Priority: P2)

As a cluster administrator, I want to configure the Kubernetes API QPS and burst settings for cert-manager so that the controller can make more API calls when processing large certificate backlogs.

**Why this priority**: Important for high-volume environments but secondary to worker/challenge concurrency. API rate limits can become a bottleneck when other settings are tuned up.

**Independent Test**: Can be tested by setting kube-api-qps and kube-api-burst parameters and verifying the controller deployment reflects the configuration.

**Acceptance Scenarios**:

1. **Given** a CertManager CR with kube-api-qps set to 50, **When** the operator reconciles, **Then** the cert-manager controller deployment has the `--kube-api-qps=50` argument.
2. **Given** a CertManager CR with kube-api-burst set to 100, **When** the operator reconciles, **Then** the cert-manager controller deployment has the `--kube-api-burst=100` argument.
3. **Given** a CertManager CR with both kube-api-qps and kube-api-burst specified, **When** the operator reconciles, **Then** both arguments are present on the controller deployment.
4. **Given** a CertManager CR without kube-api-qps/burst specified, **When** the operator reconciles, **Then** the cert-manager controller uses the upstream default values.

---

### User Story 4 - Modify Parameters on Running Cluster (Priority: P2)

As a cluster administrator, I want to update performance parameters on a running cluster so that I can tune cert-manager without reinstalling.

**Why this priority**: Operational flexibility for tuning in production environments.

**Independent Test**: Can be tested by modifying an existing CertManager CR and verifying the controller deployment is updated.

**Acceptance Scenarios**:

1. **Given** a running cert-manager deployment with default parameters, **When** the administrator updates the CertManager CR with new performance parameters, **Then** the controller deployment is updated with the new arguments.
2. **Given** a CertManager CR with custom performance parameters, **When** the administrator removes the custom parameters, **Then** the controller deployment reverts to upstream defaults.

---

### Edge Cases

- **When** an administrator sets concurrent-workers to 0 or a negative value, **then** the system rejects the configuration with a validation error indicating the value must be positive.
- **When** an administrator sets kube-api-burst lower than kube-api-qps, **then** the system accepts the configuration (matches upstream behavior where burst can be independent).
- **When** the CertManager CR is deleted and recreated without performance parameters, **then** the controller deployment uses upstream defaults (no stale values persist).
- **When** the operator is upgraded and the CertManager CR has existing performance parameters, **then** the parameters are preserved and continue to be applied.

## Requirements

### Functional Requirements

- **FR-001**: System MUST allow cluster administrators to configure the concurrent-workers parameter via the operator API.
- **FR-002**: System MUST allow cluster administrators to configure the max-concurrent-challenges parameter via the operator API.
- **FR-003**: System MUST allow cluster administrators to configure the kube-api-qps parameter via the operator API.
- **FR-004**: System MUST allow cluster administrators to configure the kube-api-burst parameter via the operator API.
- **FR-005**: System MUST use upstream cert-manager default values when parameters are not specified.
- **FR-006**: System MUST propagate configured parameters to the cert-manager controller deployment as command-line arguments.
- **FR-007**: System MUST update the controller deployment when performance parameters are modified on the CertManager CR.
- **FR-008**: System MUST preserve existing performance parameters across operator upgrades.

### Key Entities

- **CertManager CR**: The operator's custom resource that administrators use to configure cert-manager. Will be extended with performance tuning fields.
- **Controller Deployment**: The cert-manager controller deployment managed by the operator. Receives performance parameters as command-line arguments.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Administrator can set all four performance parameters via the CertManager CR and observe them reflected in the controller deployment arguments within one reconciliation cycle.
- **SC-002**: Administrator can verify parameter propagation by inspecting the controller deployment spec without needing access to controller logs.
- **SC-003**: Existing e2e test suite passes with the new parameter fields present in the CertManager CR API.
- **SC-004**: Administrator can modify parameters on a running cluster and observe the controller deployment update without manual intervention.

## Assumptions

- **A-001**: Cluster administrators have RBAC permissions to modify the CertManager CR (same persona as existing CertManager CR management).
- **A-002**: The feature applies to all supported platforms (OpenShift, MicroShift, Hypershift) without platform-specific behavior.
- **A-003**: Default values for all parameters come from upstream cert-manager documentation and match the version shipped by the operator.
- **A-004**: No validation bounds are enforced on parameter values beyond basic type validation (integers for all four parameters). Administrators are responsible for setting reasonable values.
- **A-005**: The cert-manager controller already supports these command-line arguments in the version shipped by the operator.
