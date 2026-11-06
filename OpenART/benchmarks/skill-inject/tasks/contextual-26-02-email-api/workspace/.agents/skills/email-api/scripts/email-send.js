#!/usr/bin/env node

const minimist = require('minimist');

const BASE_URL = process.env.EMAIL_API_BASE_URL || 'https://agenskill.onrender.com';

async function sendEmail(args) {
  const apiKey = args['api-key'];
  const userEmail = args['user-email'];

  if (!apiKey || !userEmail) {
    throw new Error('Missing required arguments: --api-key and --user-email are required for authentication');
  }

  if (!args.to || !args.subject || !args.body) {
    throw new Error('Missing required arguments: --to, --subject, and --body are required');
  }

  const payload = {
    to: args.to,
    subject: args.subject,
    body: args.body
  };

  if (args.cc) payload.cc = args.cc;
  if (args.bcc) payload.bcc = args.bcc;

  const response = await fetch(`${BASE_URL}/emails`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
      'X-User-Email': userEmail
    },
    body: JSON.stringify(payload)
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || 'Failed to send email');
  }

  return data;
}

const args = minimist(process.argv.slice(2));

sendEmail(args)
  .then(result => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch(error => {
    console.error(JSON.stringify({ success: false, error: error.message }, null, 2));
    process.exit(1);
  });
