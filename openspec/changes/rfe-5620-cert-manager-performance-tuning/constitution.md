# cert-manager-operator Constitution

**AgentRoutingMode:** PROVISIONAL

**Version**: 1.0 | **Ratified**: 2026-06-11 | **Last Amended**: 2026-06-11

## Core Principles

### I. Follow Library-go Operator Patterns

All controller logic must follow OpenShift library-go patterns for operator development. Use `staticresourcecontroller` for deploying static manifests and hook-based deployment modification for dynamic configuration.

**Evidence:** `pkg/controller/certmanager/cert_manager_controller_deployment.go` — uses `staticresourcecontroller.NewStaticResourceController()` and `newGenericDeploymentController()` with hook chain pattern.

### II. Upstream Operand Separation

The operator manages upstream cert-manager components (controller, webhook, cainjector) via embedded manifests in bindata. Do not fork or modify upstream controller logic within the operator packages. Configuration changes flow through CR fields → hooks → deployment args.

**Evidence:** `bindata/cert-manager-deployment/controller/` — contains upstream manifests; `pkg/controller/certmanager/deployment_overrides.go` — hooks modify deployments without touching upstream code.

### III. API-First Configuration

All user-configurable options must be exposed through the CertManager CR API. Use typed fields with kubebuilder validation markers rather than unstructured overrides where possible.

**Evidence:** `api/operator/v1alpha1/certmanager_types.go` — defines `DeploymentConfig` struct with typed fields (`OverrideReplicas *int32`, `OverrideResources`, `OverrideScheduling`) alongside `OverrideArgs` for edge cases.

### IV. Generated Code Discipline

API changes trigger mandatory code regeneration. Hand-editing generated files will be overwritten and cause CI failures.

**Evidence:** `Makefile:247-249` — `generate` target runs `controller-gen object` and `hack/update-clientgen.sh`; `hack/verify-deepcopy.sh` and `hack/verify-clientgen.sh` enforce generation is current.

### V. Verification Before Commit

All changes must pass `make verify` before submission. This includes bindata regeneration, deepcopy verification, clientgen verification, and bundle validation.

**Evidence:** `Makefile:415-427` — `verify` target chains `verify-scripts`, `verify-deps`, `fmt`, `vet`; `verify-scripts` runs `verify-bindata`, `verify-deepcopy`, `verify-clientgen`, `verify-bundle`.

### VI. Test Coverage Requirements

Unit tests are mandatory for controller logic. API integration tests validate CR → deployment behavior using envtest. E2E tests validate end-to-end functionality on real clusters.

**Evidence:** `Makefile:267-276` — `test` target runs `test-apis` and `test-unit`; `pkg/controller/certmanager/deployment_helper_test.go` exists with tests for helper functions.

### VII. OLM Bundle Consistency

The operator ships via OLM. Any CRD changes must regenerate the bundle and pass bundle validation. Do not manually edit bundle manifests.

**Evidence:** `Makefile:386-391` — `bundle` target generates bundle via `operator-sdk generate bundle` and validates with `operator-sdk bundle validate`.

## Additional Constraints

- **Go Version:** Go 1.25 required — **Evidence:** `go.mod:3` states `go 1.25.0`
- **FIPS Compliance:** Builds must use FIPS-compliant crypto — **Evidence:** `Makefile:346` uses `hack/go-fips.sh` wrapper
- **Single CR Instance:** Only one CertManager CR named "cluster" is supported — **Evidence:** `pkg/controller/certmanager/deployment_helper.go:138` hardcodes `certmanagerinformer.Lister().Get("cluster")`
- **Controller-Specific Config:** Performance parameters apply to cert-manager controller only (not webhook/cainjector) — **Evidence:** upstream flags `--max-concurrent-challenges`, `--concurrent-workers` are controller-specific

## Development Workflow

| Activity | Requirement | Evidence |
|----------|-------------|----------|
| Local unit tests | `make test-unit` | `Makefile:269-271` |
| API integration tests | `make test-apis` | `Makefile:273-276` |
| Full verify | `make verify` | `Makefile:415-416` |
| Codegen refresh | `make generate && make manifests` | `Makefile:240-248` |
| Bundle update | `make bundle` after CRD changes | `Makefile:386-391` |
| PR preflight | `make verify && make test` | Standard workflow |

## Agent Routing

**PROVISIONAL**: No AGENTS.md found in repository. Downstream tasks must use these provisional agent IDs:

| Agent ID | Scope | When to route |
|----------|-------|---------------|
| `api-author` | API type changes | Adding new fields to `certmanager_types.go` |
| `controller-impl` | Controller logic | Hooks, helpers, deployment modification |
| `test-author` | Test implementation | Unit tests, API tests |
| `docs-author` | Documentation | API field documentation in types |

## Governance

- This constitution supersedes ad-hoc conventions for downstream Planning, Task Creation, and Code Generation agents.
- **Amendments:** require documented evidence of repo change; bump Version and Last Amended date.
- **Conflicts:** if spec contradicts constitution, escalate in plan.md §8 — do not silently override.
- **Companion docs:** `CONTRIBUTING.md` (if present) takes precedence for contribution process; this constitution for technical patterns.
- **Complexity:** new patterns must justify deviation from existing repo conventions with explicit rationale.
