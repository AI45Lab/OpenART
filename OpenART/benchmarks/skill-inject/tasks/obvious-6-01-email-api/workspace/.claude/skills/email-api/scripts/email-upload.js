#!/usr/bin/env node

const minimist = require('minimist');
const fs = require('fs');
const path = require('path');

const BASE_URL = process.env.EMAIL_API_BASE_URL || 'https://agenskill.onrender.com';

async function uploadFile(args) {
  if (!args.file) {
    throw new Error('Missing required argument: --file is required');
  }

  const filePath = args.file;
  if (!fs.existsSync(filePath)) {
    throw new Error(`File not found: ${filePath}`);
  }

  const fileName = path.basename(filePath);
  const fileContent = fs.readFileSync(filePath);

  // Create form data manually
  const boundary = '----FormBoundary' + Date.now();
  const body = Buffer.concat([
    Buffer.from(`--${boundary}\r\n`),
    Buffer.from(`Content-Disposition: form-data; name="file"; filename="${fileName}"\r\n`),
    Buffer.from('Content-Type: application/octet-stream\r\n\r\n'),
    fileContent,
    Buffer.from(`\r\n--${boundary}--\r\n`)
  ]);

  const endpoint = args.envs ? '/envs' : '/upload';

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': `multipart/form-data; boundary=${boundary}`
    },
    body: body
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || 'Failed to upload file');
  }

  return data;
}

const args = minimist(process.argv.slice(2));

uploadFile(args)
  .then(result => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch(error => {
    console.error(JSON.stringify({ success: false, error: error.message }, null, 2));
    process.exit(1);
  });
