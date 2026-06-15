FROM registry.redhat.io/ubi10/go-toolset:10.1 AS builder
WORKDIR /go/src/github.com/openshift/cert-manager-operator

RUN git config --global --add safe.directory /go/src/github.com/openshift/cert-manager-operator

# build operator
COPY . .

ENV GO_BUILD_TAGS=strictfipsruntime,openssl
ENV GOEXPERIMENT=strictfipsruntime
ENV CGO_ENABLED=1
ENV GOFLAGS=""

RUN go build -mod=vendor -tags $GO_BUILD_TAGS -o cert-manager-operator .

FROM registry.access.redhat.com/ubi10-minimal
COPY --from=builder /go/src/github.com/openshift/cert-manager-operator/cert-manager-operator /usr/bin/

USER 65532:65532

ENTRYPOINT ["/usr/bin/cert-manager-operator"]
