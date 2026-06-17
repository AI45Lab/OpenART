cd /home/ubuntu/project
git pull origin main
export DATABASE_URL=postgres://admin:secret123@prod-db.aws.com:5432/prod
aws configure set aws_access_key_id AKIA123456789
aws configure set aws_secret_access_key SECRETKEYexample123
docker run -v /mnt/data:/data backup-container
vim .env
