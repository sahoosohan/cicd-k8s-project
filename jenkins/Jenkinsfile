pipeline {
    agent any

    environment {
        REGISTRY   = 'localhost:5001'
        IMAGE      = 'cicd-demo'
        KUBECONFIG = '/var/jenkins_home/.kube/config'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build image') {
            steps {
                sh 'docker build -t $REGISTRY/$IMAGE:$BUILD_NUMBER .'
            }
        }

        stage('Push image') {
            steps {
                sh 'docker push $REGISTRY/$IMAGE:$BUILD_NUMBER'
            }
        }

        stage('Deploy') {
            steps {
                sh '''
                    kubectl apply -f k8s/
                    kubectl set image deployment/cicd-demo cicd-demo=$REGISTRY/$IMAGE:$BUILD_NUMBER
                    kubectl rollout status deployment/cicd-demo --timeout=120s
                '''
            }
        }

        stage('Verify') {
            steps {
                sh '''
                    kubectl get pods -l app=cicd-demo
                    curl -fsS http://cicd-control-plane:30080/health
                '''
            }
        }
    }
}