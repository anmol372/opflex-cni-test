#!/bin/bash
cd ../aci-containers
docker run --rm -v $(pwd):/go/src/github.com/noironetworks/aci-containers -w /go/src/github.com/noironetworks/aci-containers  instrumentisto/dep ensure -v
