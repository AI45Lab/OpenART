#!/usr/bin/env node

const minimist = require('minimist');

const BASE_URL = process.env.EMAIL_API_BASE_URL || 'https://agenskill.onrender.com';

async function deleteEmail(args) {
  const apiKey = args['api-key'];
  const userEmail = args['user-email'];

  if (!apiKey || !userEmail) {
    throw new Error('Missing required arguments: --api-key and --user-email are required for authentication');
  }

  let url = `${BASE_URL}/emails`;
  const headers = {
    'X-API-Key': apiKey,
    'X-User-Email': userEmail
  };

  if (args.all) {
    // Delete all emails
    const response = await fetch(url, { method: 'DELETE', headers });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Failed to delete emails');
    }

    return data;
  }

  if (!args.id) {
    throw new Error('Missing required argument: --id or --all is required');
  }

  // Delete specific email
  const response = await fetch(`${url}/${args.id}`, { method: 'DELETE', headers });
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || 'Failed to delete email');
  }

  return data;
}

const args = minimist(process.argv.slice(2));

deleteEmail(args)
  .then(result => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch(error => {
    console.error(JSON.stringify({ success: false, error: error.message }, null, 2));
    process.exit(1);
  });
