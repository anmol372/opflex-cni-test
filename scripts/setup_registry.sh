#!/bin/bash

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
