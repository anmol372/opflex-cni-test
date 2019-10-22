#!/bin/bash
kubectl --kubeconfig=/Users/joji/go/src/opflex-cni-test/data/kubeconfig delete secret kafka-certificates
kubectl --kubeconfig=/Users/joji/go/src/opflex-cni-test/data/kubeconfig create secret generic kafka-certificates --from-file=./kafka.keystore.jks --from-file=./kafka.truststore.jks
