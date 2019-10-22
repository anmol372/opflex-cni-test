#!/bin/bash

# Step 1 generate server and client key pairs
echo "Server key pair..."
#openssl req -new -newkey rsa:2048 -nodes -keyout kafka-server.key -out kafka-server.csr
keytool -keystore kafka.keystore.jks -alias server -validity 3650 -keyalg RSA -genkey -ext SAN=DNS:ut-kafka-0.ut-kafka-headless.default.svc.cluster.local -dname "cn=ut-kafka-0.ut-kafka-headless.default.svc.cluster.local, ou=ut, o=ut, c=US" -storepass UnitTest

echo "Client key pair..."
openssl req -new -newkey rsa:2048 -nodes -subj "/C=US/ST=New Sweden/L=Stockholm /O=ut/OU=ut/CN=ut-kafka-0.ut-kafka-headless.default.svc.cluster.local/emailAddress=..." -keyout kafka-client.key -out kafka-client.csr

# Step 2 generate CA
echo "CA key pair and cert..."
openssl req -new -x509 -keyout ca.key -out ca.crt -days 3650 -nodes -subj "/C=US/ST=New Sweden/L=Stockholm /O=ut/OU=ut/CN=ut-kafka-0.ut-kafka-headless.default.svc.cluster.local/emailAddress=..."
keytool -keystore kafka.truststore.jks -alias CARoot -import -file ca.crt -storepass UnitTest

# Step 3 sign server, client certs with the CA
echo "Server cert..."
#openssl x509 -req -CA ca.crt -CAkey ca.key -in kafka-server.csr -out kafka-server.crt -days 3650 -CAcreateserial -passin pass:UnitTest

keytool -keystore kafka.keystore.jks -alias server -certreq -file cert-file -storepass UnitTest
openssl x509 -req -CA ca.crt -CAkey ca.key -in cert-file -out cert-signed -days 3650 -CAcreateserial 
keytool -keystore kafka.keystore.jks -alias CARoot -import -file ca.crt -storepass UnitTest
keytool -keystore kafka.keystore.jks -alias server -import -file cert-signed -storepass UnitTest
echo "Client cert..."
openssl x509 -req -CA ca.crt -CAkey ca.key -in kafka-client.csr -out kafka-client.crt -days 3650 -CAcreateserial 
