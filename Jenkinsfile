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
                script { env.DEPLOY_STARTED = 'true' }
                sh '''
                    kubectl apply -f k8s/
                    kubectl set image deployment/cicd-demo cicd-demo=$REGISTRY/$IMAGE:$BUILD_NUMBER
                    kubectl rollout status deployment/cicd-demo --timeout=90s
                '''
            }
        }

        stage('Verify') {
            steps {
                sh '''
                    sleep 5
                    kubectl get pods -l app=cicd-demo
                    curl -fsS http://cicd-control-plane:30080/health
                '''
            }
        }
    }

        post {
        failure {
            script {
                if (env.DEPLOY_STARTED == 'true') {
                    echo 'Deployment failed. Collecting diagnostics, then rolling back.'
                sh '''
                    sed "s|image: .*|image: $REGISTRY/$IMAGE:$BUILD_NUMBER|" k8s/deployment.yaml | kubectl apply -f -
                    kubectl apply -f k8s/service.yaml
                    kubectl rollout status deployment/cicd-demo --timeout=90s
                '''
                } else {
                    echo 'Failed before deployment, so there is nothing to roll back.'
                }
            }
        }
        success {
            echo "Build ${BUILD_NUMBER} deployed successfully."
        }
    }
}