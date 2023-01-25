package main

import "errors"

var (
	cmap1 = `apiVersion: v1
kind: ConfigMap
metadata:
  name: cmap-1
  namespace: sandbox
data:
  key: value`
	cmap2 = `apiVersion: v1
kind: ConfigMap
metadata:
	name: cmap-2
data:
	key: value`
)

func AssetGetter(name string) ([]byte, error) {
	if name == "cmap1" {
		return []byte(cmap1), nil
	} else if name == "cmap2" {
		return []byte(cmap2), nil
	} else {
		return nil, errors.New("file not found")
	}
}
