# Repository Assessment Report: RFE-5620 Performance Tuning Parameters

## §0 Assessment Metadata

| Field | Value |
|-------|-------|
| Repository | https://github.com/openshift/cert-manager-operator |
| Branch | master |
| Commit | db88f8048 (latest at assessment time) |
| Tooling Status | VERIFIED |
| Spec Status | PASS (validation score 83/100) |
| Feature Status | GREENFIELD - new API fields for performance parameters |

## §1 Architecture Overview

### 1.1 Project Type
OpenShift Operator built with library-go patterns, managing cert-manager, istio-csr, and trust-manager operands.

### 1.2 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CertManager CR (cluster)                  │
│   spec.controllerConfig.overrideArgs (existing)             │
│   spec.controllerConfig.<new performance fields> (RFE-5620) │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Operator Controller (library-go)                │
│   pkg/controller/certmanager/cert_manager_controller_deployment.go │
│   - Reads CertManager CR via informer                        │
│   - Applies deployment hooks (args, env, resources, etc.)    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│           cert-manager Controller Deployment                 │
│   bindata/cert-manager-deployment/controller/               │
│   - Arguments merged via mergeContainerArgs()               │
│   - Reconciled by staticresourcecontroller                  │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 Key Patterns for This Feature

**Argument Override Pattern**: The operator already supports `controllerConfig.overrideArgs` for arbitrary arguments. This feature adds dedicated fields for the four performance parameters, providing a better UX than raw args.

**Deployment Hook System**: `pkg/controller/certmanager/deployment_overrides.go` defines hook functions that modify deployments before apply:
- `withContainerArgsOverrideHook()` - merges additional args
- `getOverrideArgsFor()` - retrieves override args from CertManager CR

**DO NOT EDIT Traps**:
- `pkg/operator/assets/bindata.go` - generated, regenerate with `make update-bindata`
- `api/operator/v1alpha1/zz_generated.deepcopy.go` - generated, regenerate with `make generate`

## §2 Target Files for RFE-5620

### 2.1 API Types (MUST MODIFY)

| File | Purpose | Change Required |
|------|---------|-----------------|
| `api/operator/v1alpha1/certmanager_types.go` | CertManager CR spec | Add `ControllerPerformanceConfig` struct with 4 fields |

### 2.2 Controller Logic (MUST MODIFY)

| File | Purpose | Change Required |
|------|---------|-----------------|
| `pkg/controller/certmanager/deployment_helper.go` | Override retrieval helpers | Add `getPerformanceArgsFor()` function |
| `pkg/controller/certmanager/deployment_overrides.go` | Deployment hooks | Add hook to inject performance args |
| `pkg/controller/certmanager/generic_deployment_controller.go` | Controller setup | Wire new hook into controller chain |

### 2.3 Generated Files (AUTO-UPDATED)

| File | Regenerate With |
|------|-----------------|
| `api/operator/v1alpha1/zz_generated.deepcopy.go` | `make generate` |
| `config/crd/bases/operator.openshift.io_certmanagers.yaml` | `make manifests` |
| `bundle/manifests/operator.openshift.io_certmanagers.yaml` | `make bundle` |

### 2.4 Test Files (SHOULD MODIFY)

| File | Purpose |
|------|---------|
| `pkg/controller/certmanager/deployment_helper_test.go` | Unit tests for helper functions |
| `pkg/controller/certmanager/deployment_overrides_test.go` | Unit tests for override hooks |
| `test/e2e/` | E2E tests (optional for this feature per spec) |

## §3 Existing Patterns to Follow

### 3.1 API Field Pattern

From `certmanager_types.go`, the existing `DeploymentConfig` struct pattern:

```go
type DeploymentConfig struct {
    OverrideArgs      []string                         `json:"overrideArgs,omitempty"`
    OverrideEnv       []corev1.EnvVar                  `json:"overrideEnv,omitempty"`
    OverrideLabels    map[string]string                `json:"overrideLabels,omitempty"`
    OverrideResources CertManagerResourceRequirements  `json:"overrideResources,omitempty"`
    OverrideReplicas  *int32                           `json:"overrideReplicas,omitempty"`
    OverrideScheduling CertManagerScheduling           `json:"overrideScheduling,omitempty"`
}
```

**Pattern**: Add new fields to `DeploymentConfig` or create a sibling struct for performance tuning.

### 3.2 Argument Merge Pattern

From `deployment_helper.go:23-40`, `mergeContainerArgs()` handles key=value deduplication:

```go
func mergeContainerArgs(sourceArgs []string, overrideArgs []string) (destArgs []string) {
    destArgMap := map[string]string{}
    parseArgMap(destArgMap, sourceArgs)
    parseArgMap(destArgMap, overrideArgs)
    // ... builds sorted arg list
}
```

**Pattern**: Convert new fields to `--flag=value` strings and pass to `mergeContainerArgs()`.

### 3.3 Hook Registration Pattern

From `generic_deployment_controller.go`, hooks are chained:

```go
withContainerArgsOverrideHook(certManagerOperatorInformers.Operator().V1alpha1().CertManagers(), 
    deploymentName, getOverrideArgsFor),
```

## §4 Configuration Surface

### 4.1 New API Fields to Add

| Field | Type | CLI Flag | Default (upstream) |
|-------|------|----------|-------------------|
| `maxConcurrentChallenges` | `*int32` | `--max-concurrent-challenges` | 60 |
| `concurrentWorkers` | `*int32` | `--concurrent-workers` | 5 (per type) |
| `kubeAPIQPS` | `*float32` | `--kube-api-qps` | 20 |
| `kubeAPIBurst` | `*int32` | `--kube-api-burst` | 50 |

### 4.2 Reconciliation Flow

1. User updates `CertManager` CR with performance fields
2. Operator informer triggers reconciliation
3. `getPerformanceArgsFor()` reads new fields from CR
4. Hook converts fields to CLI args: `--max-concurrent-challenges=120`
5. `mergeContainerArgs()` merges with existing args
6. Deployment updated with new args
7. Controller pod restarts with tuned parameters

## §5 Reusable Assets

| Asset | Use For | Location |
|-------|---------|----------|
| `mergeContainerArgs()` | Merge performance args with existing | `pkg/controller/certmanager/deployment_helper.go` |
| `withContainerArgsOverrideHook()` | Create hook for new args | `pkg/controller/certmanager/deployment_overrides.go` |
| `getOverrideArgsFor()` | Template for `getPerformanceArgsFor()` | `pkg/controller/certmanager/deployment_helper.go` |
| `CertManagerInformer` | Access CR from hooks | `pkg/operator/informers/` |

## §6 Architectural Guardrails

### Structural
- **One CR pattern**: Single `CertManager` CR named "cluster" per cluster
- **Controller-specific config**: Performance fields go in `ControllerConfig`, not top-level spec

### API / Schema
- **Optional fields**: Use pointers (`*int32`) for optional numeric fields
- **No defaults in CRD**: Let upstream cert-manager apply defaults when fields are nil
- **Kubebuilder markers**: Add validation markers (e.g., `+kubebuilder:validation:Minimum=1`)

### Build / Tooling
- **Go 1.25**: Check `go.mod` for version requirements
- **FIPS build**: Use `hack/go-fips.sh` wrapper for builds

### Code Generation
- **DeepCopy**: Any new struct needs `+k8s:deepcopy-gen` or embedding in existing generated types
- **CRD regen**: `make manifests` after API changes

## §7 Change Cascade Checklist

| When you change... | You must also... | Verify with... |
|---|---|---|
| `api/operator/v1alpha1/certmanager_types.go` | Regenerate deepcopy, CRD, bundle | `make generate && make manifests && make bundle` |
| Any `pkg/` Go file | Run unit tests | `make test-unit` |
| Deployment hook logic | Run API tests | `make test-apis` |
| CRD schema | Verify bundle | `make verify-bundle` |

## §8 Test & CI Reference

### 8.1 Test Structure
- **Unit tests**: `pkg/controller/certmanager/*_test.go`
- **API integration tests**: `test/apis/` (uses envtest)
- **E2E tests**: `test/e2e/` (requires real cluster)

### 8.2 How to Run Tests Locally
```bash
# Unit tests
make test-unit

# API integration tests  
make test-apis

# E2E tests (requires cluster)
make test-e2e
```

### 8.3 CI Pipeline
- Prow jobs in `openshift/release` repo
- Required: `verify`, `unit`, `e2e`
- E2E uses label filter: `Platform: isSubsetOf {AWS,Generic}`

### 8.4 Test Coverage for This Feature
- Unit tests for `getPerformanceArgsFor()` function
- Unit tests for arg-to-CLI conversion
- API test verifying deployment gets updated args
- E2E: existing tests should pass (no new e2e required per spec)

## §9 Developer Workflow

### 9.1 Key Commands Reference

| Command | Purpose |
|---------|---------|
| `make build` | Build operator binary with checks |
| `make generate` | Regenerate deepcopy code |
| `make manifests` | Regenerate CRD/RBAC manifests |
| `make bundle` | Regenerate OLM bundle |
| `make verify` | Run all verification checks |
| `make test` | Run all tests |
| `make local-run` | Run operator locally |

### 9.2 Version Variables
- `CERT_MANAGER_VERSION`: v1.19.4 (in Makefile)
- `BUNDLE_VERSION`: 1.19.0 (in Makefile)

### 9.3 Local Development Setup
```bash
# Build
make build

# Run locally (requires kubeconfig)
make local-run
```

### 9.4 How to Add a New API Field

1. Edit `api/operator/v1alpha1/certmanager_types.go`
2. Add field with JSON tag and kubebuilder markers
3. Run `make generate` (deepcopy)
4. Run `make manifests` (CRD)
5. Run `make bundle` (OLM bundle)
6. Add controller logic to read/use the field
7. Add unit tests
8. Run `make verify && make test`

## §10 Platform & Environment Integration

### 10.1 Platform Applicability
Per spec A-002: Platform independent - applies to OpenShift, MicroShift, and Hypershift without special handling.

### 10.2 Security Considerations
- Performance parameters don't expand RBAC requirements
- No secrets or credentials involved
- Parameters are cluster-admin controlled via CertManager CR

## §11 Risks & Downstream Impacts

### 11.1 Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| High QPS/burst values could overload API server | Cluster instability | Document recommended ranges; no validation enforcement per spec A-004 |
| Interaction with `overrideArgs` | User might set same param twice | `mergeContainerArgs()` deduplicates by key; dedicated field wins (last writer) |

### 11.2 UNVERIFIED Items
- Exact upstream default values should be verified against cert-manager v1.19.4 docs
- Interaction with ACME solver image override (should be independent)

## §12 Quick Reference Card

### Preflight Checklist
```bash
1. make generate
2. make manifests  
3. make bundle
4. make verify
5. make test
```

### Key File Quick-Nav

| I want to... | Look at... |
|---|---|
| Add performance API fields | `api/operator/v1alpha1/certmanager_types.go` |
| Add controller hook | `pkg/controller/certmanager/deployment_overrides.go` |
| Add helper function | `pkg/controller/certmanager/deployment_helper.go` |
| Wire hook to controller | `pkg/controller/certmanager/generic_deployment_controller.go` |
| Add unit test | `pkg/controller/certmanager/deployment_helper_test.go` |
| Check deployment manifest | `bindata/cert-manager-deployment/controller/cert-manager-deployment.yaml` |
