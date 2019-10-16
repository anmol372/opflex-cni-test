### Create topics

```bash
kubectl exec -it confluent-client -- /usr/bin/kafka-topics --zookeeper unit-test-zookeeper --topic topic1 --create --partitions 3 --replication-factor 1
```

### List topics

```bash
kubectl exec -it confluent-client -- /usr/bin/kafka-topics --zookeeper unit-test-zookeeper:2181 --list
```

### Describe topics

```bash
kubectl exec -it confluent-client -- /usr/bin/kafka-topics --zookeeper unit-test-zookeeper:2181 --describe
```

### Produce messages

```bash
kubectl exec -it confluent-client -- /usr/bin/kafka-console-producer --broker-list unit-test-kafka:9092 --topic topic1
```

### Consume messages

```bash
kubectl exec -it confluent-client -- /usr/bin/kafka-console-consumer --bootstrap-server unit-test-kafka:9092 --topic topic1 --from-beginning
```

### Delete topic

```bash
kubectl exec -it confluent-client -- /usr/bin/kafka-topics --zookeeper unit-test-zookeeper:2181 --delete --topic topic1
```
