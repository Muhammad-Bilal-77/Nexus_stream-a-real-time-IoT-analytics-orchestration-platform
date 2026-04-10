const nodemailer = require('nodemailer');
const logger = require('./logger');

const transporter = nodemailer.createTransport({
    host: 'smtp.gmail.com',
    port: 587,
    secure: false, // true for 465, false for other ports
    auth: {
        user: 'evolvoria@gmail.com',
        pass: 'vgdz xdho izlo wglk'
    }
});

async function sendMagicLinkEmail(toEmail, magicLink) {
    try {
        const info = await transporter.sendMail({
            from: '"NexusStream Auth" <evolvoria@gmail.com>', // sender address
            to: toEmail, // list of receivers
            subject: 'Your NexusStream Magic Login Link \u2728', // Subject line
            text: `Welcome back!\n\nClick the link below to securely login to your NexusStream dashboard. The link expires in 10 minutes.\n\n${magicLink}\n\nIf you did not request this, please ignore this email.`,
            html: `
            <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; background-color: #1a1a1a; color: #f5f5f5; padding: 30px; border-radius: 12px; border: 1px solid #333;">
                <h2 style="color: #60a5fa; margin-top: 0;">NexusStream Authentication</h2>
                <p style="font-size: 16px; line-height: 1.5; color: #d4d4d4;">
                    Welcome back! Click the secure button below to login to your workspace. 
                    <br/><br/>
                    <strong>This link expires in 10 minutes and can only be used once.</strong>
                </p>
                <div style="margin: 30px 0; text-align: center;">
                    <a href="${magicLink}" style="background-color: #2563eb; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; display: inline-block;">Login to NexusStream \u2192</a>
                </div>
                <p style="font-size: 12px; color: #888;">If you did not request this login, you can safely ignore this email.</p>
                <hr style="border-color: #333; margin-top: 30px;" />
                <p style="font-size: 11px; color: #666; word-break: break-all;">Trouble clicking? Copy this URL: <br/>${magicLink}</p>
            </div>
            `,
        });
        logger.info({ event: 'magic_link_email_sent', messageId: info.messageId, email: toEmail });
    } catch (error) {
        logger.error({ event: 'magic_link_email_error', error: error.message });
        throw error;
    }
}

module.exports = { sendMagicLinkEmail };
