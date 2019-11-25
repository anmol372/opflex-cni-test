#!/bin/bash
kubectl --kubeconfig=/Users/joji/go/src/opflex-cni-test/data/kubeconfig delete secret kafka-certificates
kubectl --kubeconfig=/Users/joji/go/src/opflex-cni-test/data/kubeconfig delete secret kafka-client-certificates -n kube-system
kubectl --kubeconfig=/Users/joji/go/src/opflex-cni-test/data/kubeconfig delete secret kafka-kv-certificates
kubectl --kubeconfig=/Users/joji/go/src/opflex-cni-test/data/kubeconfig create secret generic kafka-certificates --from-file=./kafka.keystore.jks --from-file=./kafka.truststore.jks
kubectl --kubeconfig=/Users/joji/go/src/opflex-cni-test/data/kubeconfig create secret generic kafka-client-certificates --from-file=./ca.crt --from-file=./kafka-client.crt --from-file=./kafka-client.key -n kube-system
kubectl --kubeconfig=/Users/joji/go/src/opflex-cni-test/data/kubeconfig create secret generic kafka-kv-certificates --from-file=./ca.crt --from-file=./kafka-client.crt --from-file=./kafka-client.key
