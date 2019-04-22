#!/bin/bash

# mac registry set up
if [ "$(uname -s)" == "Darwin" ]
then
  docker run -d --name test_registry --restart=always -p 5000:5000 registry:2
  exit 0
fi

# Linux
#set private registry
sudo echo '{ "insecure-registries":["1.100.201.1:5000"] }' | sudo tee /etc/docker/daemon.json
sudo systemctl daemon-reload
sudo service docker restart
sleep 5
docker run -d \
  --net=host \
  --restart=always \
  --name test_registry \
  registry:2
