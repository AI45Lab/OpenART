#!/usr/bin/env node

const minimist = require('minimist');

const BASE_URL = process.env.EMAIL_API_BASE_URL || 'https://agenskill.onrender.com';

async function searchEmails(args) {
  const apiKey = args['api-key'];
  const userEmail = args['user-email'];

  if (!apiKey || !userEmail) {
    throw new Error('Missing required arguments: --api-key and --user-email are required for authentication');
  }

  const params = new URLSearchParams();

  if (args.folder) params.append('folder', args.folder);
  if (args.status) params.append('status', args.status);
  if (args.limit) params.append('limit', args.limit);

  const url = `${BASE_URL}/emails${params.toString() ? '?' + params.toString() : ''}`;

  const response = await fetch(url, {
    headers: {
      'X-API-Key': apiKey,
      'X-User-Email': userEmail
    }
  });
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || 'Failed to search emails');
  }

  return {
    success: true,
    count: data.emails ? data.emails.length : 0,
    emails: data.emails || []
  };
}

const args = minimist(process.argv.slice(2));

searchEmails(args)
  .then(result => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch(error => {
    console.error(JSON.stringify({ success: false, error: error.message }, null, 2));
    process.exit(1);
  });
