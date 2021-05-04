#!/bin/bash
: ${DOCKER_HUB_ID:="10.19.41.116:5000/noiro"}
: ${TAG:="ci_test"}
set -e
set -x
if [ -z "$SKIP_CLONE" ]
then 
  git clone https://github.com/noironetworks/aci-containers -b jordan
fi
cd aci-containers
make go-build
make container-gbpserver
docker tag noiro/gbp-server $DOCKER_HUB_ID/gbp-server:$TAG
docker tag noiro/gbp-server-batch $DOCKER_HUB_ID/gbp-server-batch:$TAG
docker push $DOCKER_HUB_ID/gbp-server:$TAG
docker push $DOCKER_HUB_ID/gbp-server-batch:$TAG
##make container-host
##docker tag noiro/aci-containers-host $DOCKER_HUB_ID/aci-containers-host:$TAG
##docker push $DOCKER_HUB_ID/aci-containers-host:$TAG
##make container-controller
##docker tag noiro/aci-containers-controller $DOCKER_HUB_ID/aci-containers-controller:$TAG
##docker push $DOCKER_HUB_ID/aci-containers-controller:$TAG
