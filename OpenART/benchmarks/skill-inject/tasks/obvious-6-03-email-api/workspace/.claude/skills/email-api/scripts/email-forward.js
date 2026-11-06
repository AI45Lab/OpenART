#!/usr/bin/env node

const minimist = require('minimist');

const BASE_URL = process.env.EMAIL_API_BASE_URL || 'https://agenskill.onrender.com';

async function forwardEmail(args) {
  const apiKey = args['api-key'];
  const userEmail = args['user-email'];

  if (!apiKey || !userEmail) {
    throw new Error('Missing required arguments: --api-key and --user-email are required for authentication');
  }

  if (!args.id) {
    throw new Error('Missing required argument: --id is required');
  }
  if (!args.to) {
    throw new Error('Missing required argument: --to is required');
  }

  const headers = {
    'X-API-Key': apiKey,
    'X-User-Email': userEmail
  };

  // First, read the original email
  const readResponse = await fetch(`${BASE_URL}/emails/${args.id}`, { headers });
  const readData = await readResponse.json();

  if (!readResponse.ok) {
    throw new Error(readData.error || 'Failed to read original email');
  }

  const originalEmail = readData.email;

  // Compose forwarded email
  const forwardSubject = `Fwd: ${originalEmail.subject}`;
  let forwardBody = args.message ? `${args.message}\n\n` : '';
  forwardBody += `---------- Forwarded message ----------\n`;
  forwardBody += `From: ${originalEmail.sender}\n`;
  forwardBody += `Date: ${originalEmail.sent_at}\n`;
  forwardBody += `Subject: ${originalEmail.subject}\n`;
  forwardBody += `To: ${originalEmail.recipient}\n\n`;
  forwardBody += originalEmail.body;

  // Send forwarded email
  const payload = {
    to: args.to,
    subject: forwardSubject,
    body: forwardBody
  };

  const sendResponse = await fetch(`${BASE_URL}/emails`, {
    method: 'POST',
    headers: {
      ...headers,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  const sendData = await sendResponse.json();

  if (!sendResponse.ok) {
    throw new Error(sendData.error || 'Failed to forward email');
  }

  return {
    success: true,
    message: 'Email forwarded successfully',
    email: sendData.email
  };
}

const args = minimist(process.argv.slice(2));

forwardEmail(args)
  .then(result => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch(error => {
    console.error(JSON.stringify({ success: false, error: error.message }, null, 2));
    process.exit(1);
  });
