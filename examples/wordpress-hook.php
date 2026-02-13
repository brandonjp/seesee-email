<?php
/**
 * SeeSee — WordPress Email Logging Hook
 *
 * Drop into your theme's functions.php or a must-use plugin.
 * Automatically logs every email sent by wp_mail().
 *
 * Define these constants in wp-config.php:
 *   define('SEESEE_URL', 'https://seesee.example.com');
 *   define('SEESEE_API_KEY', 'ss_your_api_key_here');
 */

add_action('wp_mail_succeeded', function ($mail_data) {
    if (! defined('SEESEE_URL') || ! defined('SEESEE_API_KEY')) {
        return;
    }

    wp_remote_post(SEESEE_URL . '/api/v1/log', [
        'headers' => [
            'Authorization' => 'Bearer ' . SEESEE_API_KEY,
            'Content-Type'  => 'application/json',
        ],
        'body' => json_encode([
            'to'        => (array) $mail_data['to'],
            'from'      => $mail_data['headers']['From'] ?? get_option('admin_email'),
            'subject'   => $mail_data['subject'],
            'body_html' => $mail_data['message'],
            'body_text' => wp_strip_all_tags($mail_data['message']),
            'status'    => 'sent',
            'provider'  => 'wp_mail',
        ]),
        'blocking' => false,
    ]);
});

add_action('wp_mail_failed', function ($error) {
    if (! defined('SEESEE_URL') || ! defined('SEESEE_API_KEY')) {
        return;
    }

    wp_remote_post(SEESEE_URL . '/api/v1/log', [
        'headers' => [
            'Authorization' => 'Bearer ' . SEESEE_API_KEY,
            'Content-Type'  => 'application/json',
        ],
        'body' => json_encode([
            'to'            => [],
            'from'          => get_option('admin_email'),
            'subject'       => 'Unknown',
            'status'        => 'failed',
            'error_message' => $error->get_error_message(),
            'provider'      => 'wp_mail',
        ]),
        'blocking' => false,
    ]);
});
