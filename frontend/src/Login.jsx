import React, { useState } from 'react';
import './Login.css';

function Login({ onLoginSuccess }) {
  const [isLoginMode, setIsLoginMode] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const toggleMode = () => {
    setIsLoginMode(!isLoginMode);
    setUsername('');
    setPassword('');
    setConfirmPassword('');
    setError('');
    setMessage('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');

    if (!username.trim() || !password) {
      setError('Please fill in all fields.');
      return;
    }

    if (!isLoginMode && password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    const API_URL = import.meta.env.VITE_API_URL || '';
    const endpoint = isLoginMode ? '/api/login' : '/api/register';

    try {
      const response = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: username.trim(),
          password: password,
        }),
      });

      const responseText = await response.text();
      let data = {};
      try {
        data = responseText ? JSON.parse(responseText) : {};
      } catch (jsonErr) {
        throw new Error(`Server error: ${responseText.substring(0, 200)}`);
      }

      if (!response.ok) {
        throw new Error(data.error || 'Authentication failed.');
      }

      if (isLoginMode) {
        onLoginSuccess(data.token, data.username);
      } else {
        setMessage('Registration successful! You can now log in.');
        setIsLoginMode(true);
        setPassword('');
        setConfirmPassword('');
      }
    } catch (err) {
      setError(err.message || 'An error occurred. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="logo-spark">✨</div>
          <h2>PranaAI</h2>
          <p className="login-subtitle">Your Personalized Ayurvedic Concierge</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          {error && <div className="auth-alert error">{error}</div>}
          {message && <div className="auth-alert success">{message}</div>}

          <div className="input-group">
            <label htmlFor="username">Username</label>
            <input
              type="text"
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your username"
              disabled={loading}
              required
            />
          </div>

          <div className="input-group">
            <label htmlFor="password">Password</label>
            <input
              type="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              disabled={loading}
              required
            />
          </div>

          {!isLoginMode && (
            <div className="input-group">
              <label htmlFor="confirmPassword">Confirm Password</label>
              <input
                type="password"
                id="confirmPassword"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm your password"
                disabled={loading}
                required
              />
            </div>
          )}

          <button type="submit" className="auth-button" disabled={loading}>
            {loading ? (
              <span className="button-spinner"></span>
            ) : isLoginMode ? (
              'Sign In'
            ) : (
              'Create Account'
            )}
          </button>
        </form>

        <div className="login-footer">
          {isLoginMode ? (
            <p>
              New to PranaAI?{' '}
              <button type="button" className="mode-toggle-link" onClick={toggleMode}>
                Register here
              </button>
            </p>
          ) : (
            <p>
              Already have an account?{' '}
              <button type="button" className="mode-toggle-link" onClick={toggleMode}>
                Sign In
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default Login;
