import React, { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function SignUpPage() {
  const { register, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await register(fullName, email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || "Registration failed");
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
        <p className="zen-auth-subtitle">Create your account</p>

        <form className="zen-auth-form" onSubmit={onSubmit}>
          <label className="zen-field zen-field-dark">
            <span className="zen-field-icon">👤</span>
            <input
              type="text"
              placeholder="Full name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
              required
            />
          </label>
          <label className="zen-field zen-field-dark">
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
          <label className="zen-field zen-field-dark">
            <span className="zen-field-icon">🔒</span>
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              minLength={6}
              required
            />
          </label>

          {error && <p className="zen-auth-error">{error}</p>}

          <button type="submit" className="zen-btn-primary" disabled={submitting}>
            {submitting ? "Creating…" : "Create account →"}
          </button>
        </form>

        <p className="zen-auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
