import React, { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message || "Sign in failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="zen-auth-page">
      <div className="zen-auth-card">
        <div className="zen-auth-logo-wrap">
          <div className="zen-auth-logo">✦</div>
        </div>
        <h1 className="zen-auth-title">Zen Agent</h1>
        <p className="zen-auth-subtitle">Welcome back</p>

        <form className="zen-auth-form" onSubmit={onSubmit}>
          <label className="zen-field">
            <span className="zen-field-icon">✉</span>
            <input
              type="email"
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </label>
          <label className="zen-field">
            <span className="zen-field-icon">🔒</span>
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>

          {error && <p className="zen-auth-error">{error}</p>}

          <button type="submit" className="zen-btn-primary" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in →"}
          </button>
        </form>

        <p className="zen-auth-footer">
          Don&apos;t have an account? <Link to="/signup">Sign up</Link>
        </p>
      </div>
    </div>
  );
}
