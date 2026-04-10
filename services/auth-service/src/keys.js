/**
 * NexusStream Auth Service — RSA Keypair Manager
 * Automatically generates a 2048-bit RS256 keypair in memory.
 */
'use strict';

const crypto = require('crypto');
const logger = require('./logger');

let publicKeyPEM = null;
let privateKeyPEM = null;

function generateKeys() {
  if (publicKeyPEM && privateKeyPEM) return;

  logger.info({ event: 'generating_rsa_keypair', message: 'Generating ephemeral RS256 keypair for development...' });
  
  const { publicKey, privateKey } = crypto.generateKeyPairSync('rsa', {
    modulusLength: 2048,
    publicKeyEncoding: {
      type: 'spki',
      format: 'pem'
    },
    privateKeyEncoding: {
      type: 'pkcs8',
      format: 'pem'
    }
  });

  publicKeyPEM = publicKey;
  privateKeyPEM = privateKey;
  
  logger.info({ event: 'rsa_keypair_ready', message: 'Keypair generated successfully' });
}

function getPublicKey() {
  if (!publicKeyPEM) generateKeys();
  return publicKeyPEM;
}

function getPrivateKey() {
  if (!privateKeyPEM) generateKeys();
  return privateKeyPEM;
}

module.exports = {
  generateKeys,
  getPublicKey,
  getPrivateKey
};
