#!/bin/bash
docker run -d \
  --net=host \
  --restart=always \
  --name test_registry \
  registry:2
