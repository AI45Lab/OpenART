#!/usr/bin/env node

const BASE_URL = process.env.EMAIL_API_BASE_URL || 'https://agenskill.onrender.com';

async function checkHealth() {
  const response = await fetch(`${BASE_URL}/health`);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || 'Health check failed');
  }

  return {
    success: true,
    status: data.status,
    uptime: data.uptime
  };
}

checkHealth()
  .then(result => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch(error => {
    console.error(JSON.stringify({ success: false, error: error.message }, null, 2));
    process.exit(1);
  });
