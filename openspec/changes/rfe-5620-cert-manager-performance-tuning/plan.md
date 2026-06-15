# Technical Implementation Plan
**Feature:** Cert-Manager Performance Tuning Parameters (RFE-5620)

## 0. Inputs acknowledged

| Input | Status |
|-------|--------|
| Spec source | RFE-5620 — validated_specs.md (PASS, score 83/100) |
| Repo assessment pin | https://github.com/openshift/cert-manager-operator, branch master, commit db88f8048 (tooling_status: VERIFIED) |
| `agents.md` | NOT PROVIDED — using provisional capability taxonomy |
| `spec_validator_results.json` | PROVIDED — validation.json |
| `constitution.md` | PROVIDED — AgentRoutingMode: PROVISIONAL |

## 1. Architectural strategy

### Overview

This feature exposes four cert-manager controller performance tuning parameters as dedicated fields on the CertManager CR API. The parameters control concurrency and API rate limits:
- `--max-concurrent-challenges` (ACME challenge parallelism)
- `--concurrent-workers` (controller worker count)
- `--kube-api-qps` (Kubernetes API QPS limit)
- `--kube-api-burst` (Kubernetes API burst limit)

### Integration Approach

The implementation follows the established operator pattern for deployment customization:
1. **API Layer**: Add new typed fields to `DeploymentConfig` struct in `certmanager_types.go`
2. **Controller Layer**: Create a new helper function and hook to read the new fields and convert to CLI arguments
3. **Deployment Layer**: Leverage existing `mergeContainerArgs()` infrastructure to inject args into the controller deployment

### Repo-grounded reality check

Per repo-assessment.md §0, this is **GREENFIELD** for the dedicated API fields. The repo currently supports arbitrary argument override via `controllerConfig.overrideArgs`, but has no dedicated performance tuning fields. The implementation follows the established pattern seen in existing `DeploymentConfig` fields (`OverrideReplicas`, `OverrideResources`, `OverrideScheduling`).

Key evidence from repo-assessment:
- `api/operator/v1alpha1/certmanager_types.go` defines existing override fields as templates
- `pkg/controller/certmanager/deployment_helper.go` contains `getOverride*For()` helpers to follow
- `pkg/controller/certmanager/deployment_overrides.go` contains hook patterns to replicate

## 2. Persistence & state

- **Kubernetes objects**: CertManager CR is source-of-truth. Performance parameters stored as optional fields in `spec.controllerConfig`.
- **Operand config/state**: Parameters are converted to CLI arguments on the cert-manager controller Deployment. No ConfigMaps or Secrets involved.
- **External/platform-injected state**: N/A — no external state dependencies.

## 3. Interfaces & contracts (operator-native)

### 3.1 Kubernetes APIs (CRDs/CRs)

**New API fields** (all optional, pointer types):

```
spec:
  controllerConfig:
    maxConcurrentChallenges: <int32>   # maps to --max-concurrent-challenges
    concurrentWorkers: <int32>         # maps to --concurrent-workers  
    kubeAPIQPS: <float32>              # maps to --kube-api-qps
    kubeAPIBurst: <int32>              # maps to --kube-api-burst
```

**Validation rules**:
- All fields optional (nil = use upstream default)
- Minimum value of 1 for integer fields (kubebuilder marker)
- No maximum enforced (per spec A-004, user responsibility)

**Immutability**: None — fields can be changed at any time, triggering deployment update.

### 3.2 Controller/runtime interfaces (internal)

**New helper function**: `getPerformanceArgsFor()` in `deployment_helper.go`
- Input: CertManagerInformer, deploymentName
- Output: `[]string` of CLI arguments, error
- Logic: Read CR, extract performance fields, convert non-nil to `--flag=value` strings

**Hook integration**: Wire into existing hook chain in `generic_deployment_controller.go`

### 3.3 Webhooks / admission (if applicable)

N/A — no webhook changes required. Kubebuilder validation markers handle field validation at admission.

### 3.4 RBAC / security boundaries (if applicable)

N/A — no RBAC changes required. Existing CertManager CR RBAC covers the new fields.

### 3.5 Packaging / OLM (if applicable)

**Bundle update required**: CRD changes require bundle regeneration via `make bundle`. No CSV changes beyond automatic CRD inclusion.

## 4. Dependencies & sequencing graph

### Critical path

1. **API Definition** → 2. **Code Generation** → 3. **Controller Logic** → 4. **Tests** → 5. **Bundle Update**

### Parallelizable workstreams

- Unit tests can be developed alongside controller logic (Phase 3 + Phase 4)
- Documentation can be drafted during any phase

### Explicit blockers / external dependencies

None — all work is self-contained within cert-manager-operator repository.

## 5. Implementation phases (logical sequence; NOT tasks)

### Phase 1: API Definition

- **Goal:** Define new performance tuning fields in CertManager CR API
- **Dependencies:** None (starting point)
- **Target files:**
  - `api/operator/v1alpha1/certmanager_types.go` — add fields to `DeploymentConfig` struct
- **Required capabilities:** API (provisional)
- **Verification hooks:** `make generate` succeeds, `make manifests` succeeds

### Phase 2: Code Generation

- **Goal:** Regenerate deepcopy, CRD manifests, and clientgen after API changes
- **Dependencies:** Phase 1 complete
- **Target files:**
  - `api/operator/v1alpha1/zz_generated.deepcopy.go` (generated)
  - `config/crd/bases/operator.openshift.io_certmanagers.yaml` (generated)
- **Required capabilities:** API (provisional)
- **Verification hooks:** `make verify` passes (includes verify-deepcopy, verify-clientgen)

### Phase 3: Controller Logic

- **Goal:** Implement helper function and hook to inject performance args into controller deployment
- **Dependencies:** Phase 2 complete (generated types available)
- **Target files:**
  - `pkg/controller/certmanager/deployment_helper.go` — add `getPerformanceArgsFor()` function
  - `pkg/controller/certmanager/deployment_overrides.go` — add hook if needed (may reuse existing)
  - `pkg/controller/certmanager/generic_deployment_controller.go` — wire hook into chain
- **Required capabilities:** OperatorController (provisional)
- **Verification hooks:** `make build` succeeds, `make vet` passes

### Phase 4: Unit Tests

- **Goal:** Add unit tests for new helper function and arg conversion logic
- **Dependencies:** Phase 3 complete
- **Target files:**
  - `pkg/controller/certmanager/deployment_helper_test.go` — tests for `getPerformanceArgsFor()`
- **Required capabilities:** Testing (provisional)
- **Verification hooks:** `make test-unit` passes with new tests

### Phase 5: Bundle and Final Verification

- **Goal:** Regenerate OLM bundle and run full verification
- **Dependencies:** Phase 4 complete
- **Target files:**
  - `bundle/manifests/operator.openshift.io_certmanagers.yaml` (generated)
- **Required capabilities:** OLMRelease (provisional)
- **Verification hooks:** `make bundle`, `make verify`, `make test`

## 6. Verification matrix (maps to spec acceptance)

| Category | Coverage | Files / Suites |
|----------|----------|----------------|
| Unit | `getPerformanceArgsFor()` arg conversion, nil handling, all 4 params | `pkg/controller/certmanager/deployment_helper_test.go` |
| Integration | API integration via envtest — CR with perf fields accepted | `test/apis/` (existing suite) |
| E2E | Existing e2e suite passes (FR: existing tests must pass) | `test/e2e/` — no new e2e per spec |
| Manual / Cluster | Verify deployment args updated after CR change | `oc get deployment cert-manager -n cert-manager -o yaml` |
| N/A | Performance benchmarking deferred per spec (optional future) | — |

## 7. Risks, migrations, and operational follow-ups

### Upgrade/migration

**Low risk**: New fields are optional with nil defaults. Existing CertManager CRs continue working unchanged. No migration required.

### Compatibility (OpenShift/MicroShift/Hypershift)

**No special handling**: Per spec A-002, feature is platform-independent. All platforms use same controller deployment pattern.

### Upstream API drift risks

**Low risk**: The four CLI flags are stable upstream cert-manager parameters. Version pinned to v1.19.4 in operator.

### Interaction with overrideArgs

**Consideration**: Users could set the same parameter via both dedicated field and `overrideArgs`. The `mergeContainerArgs()` function deduplicates by key — last writer wins. Document that dedicated fields take precedence (processed after overrideArgs in hook chain).

## 8. Open questions / SME decisions

| Question | Owner | Default Assumption |
|----------|-------|-------------------|
| Should dedicated fields override or be overridden by `overrideArgs`? | Operator maintainer | Dedicated fields processed last → win on conflict |
| Should we add validation bounds (e.g., max QPS)? | Operator maintainer | No bounds per spec A-004; user responsibility |
| Float32 for kubeAPIQPS — is this the correct Go type? | Upstream cert-manager | Yes — upstream uses float64, but float32 sufficient for QPS values |

All questions have default assumptions — no blockers for proceeding.
