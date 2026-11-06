#!/usr/bin/env node

const minimist = require('minimist');

const BASE_URL = process.env.EMAIL_API_BASE_URL || 'https://agenskill.onrender.com';

async function getContacts(args) {
  const apiKey = args['api-key'];
  const userEmail = args['user-email'];

  if (!apiKey || !userEmail) {
    throw new Error('Missing required arguments: --api-key and --user-email are required for authentication');
  }

  const response = await fetch(`${BASE_URL}/contacts`, {
    headers: {
      'X-API-Key': apiKey,
      'X-User-Email': userEmail
    }
  });
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || 'Failed to get contacts');
  }

  return {
    success: true,
    count: data.contacts ? data.contacts.length : 0,
    contacts: data.contacts || []
  };
}

const args = minimist(process.argv.slice(2));

getContacts(args)
  .then(result => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch(error => {
    console.error(JSON.stringify({ success: false, error: error.message }, null, 2));
    process.exit(1);
  });
