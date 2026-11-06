#!/usr/bin/env node

const minimist = require('minimist');

const BASE_URL = process.env.EMAIL_API_BASE_URL || 'https://agenskill.onrender.com';

async function manageNumbers(args) {
  const action = args.action || 'list';

  if (action === 'store') {
    if (args.value === undefined) {
      throw new Error('Missing required argument: --value is required for store action');
    }

    const response = await fetch(`${BASE_URL}/numbers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: args.value })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Failed to store number');
    }

    return data;
  }

  if (action === 'list') {
    const response = await fetch(`${BASE_URL}/numbers`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Failed to list numbers');
    }

    return {
      success: true,
      count: data.numbers ? data.numbers.length : 0,
      numbers: data.numbers || []
    };
  }

  throw new Error(`Unknown action: ${action}. Use --action store or --action list`);
}

const args = minimist(process.argv.slice(2));

manageNumbers(args)
  .then(result => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch(error => {
    console.error(JSON.stringify({ success: false, error: error.message }, null, 2));
    process.exit(1);
  });
