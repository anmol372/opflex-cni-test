#!/bin/bash
: ${DOCKER_HUB_ID:="1.100.201.1:5000"}
: ${TAG:="ci_test"}
set -e
if [ -z "$SKIP_CLONE" ]
then 
  git clone https://github.com/noironetworks/aci-containers
fi
cd aci-containers
make go-build
make container-gbpserver
docker tag $DOCKER_HUB_ID/gbp-server $DOCKER_HUB_ID/gbp-server:$TAG
docker tag $DOCKER_HUB_ID/gbp-server-batch $DOCKER_HUB_ID/gbp-server-batch:$TAG
docker push $DOCKER_HUB_ID/gbp-server:$TAG
docker push $DOCKER_HUB_ID/gbp-server-batch:$TAG
make container-host
docker tag $DOCKER_HUB_ID/aci-containers-host $DOCKER_HUB_ID/aci-containers-host:$TAG
docker push $DOCKER_HUB_ID/aci-containers-host:$TAG
make container-controller
docker tag $DOCKER_HUB_ID/aci-containers-controller $DOCKER_HUB_ID/aci-containers-controller:$TAG
docker push $DOCKER_HUB_ID/aci-containers-controller:$TAG
