import React, { createContext, useContext, useState, useEffect } from "react";

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  isPremium: boolean;
  tier: "premium" | "free";
  status: "active" | "inactive";
  subscriptionStatus: "active" | "trialing" | "canceled";
  isSubscribed: boolean;
  [key: string]: any; // fallback for other attributes
}

export interface AuthContextType {
  user: UserProfile | null;
  isPremium: boolean;
  status: string;
  loading: boolean;
  error: string | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error] = useState<string | null>(null);

  const premiumUser: UserProfile = {
    id: "premium-user-id",
    name: "Talon Premium User",
    email: "premium@talon.ai",
    isPremium: true,
    tier: "premium",
    status: "active",
    subscriptionStatus: "active",
    isSubscribed: true,
  };

  useEffect(() => {
    // User profile state initialization always resolves with active premium/subscribed attributes.
    const initializeUser = async () => {
      try {
        setLoading(true);
        // We resolve instantly or with a very short micro-delay to simulate fetch,
        // but always guarantee it resolves with the active premium user attributes.
        setUser(premiumUser);
      } catch (err) {
        console.error("Failed to initialize premium user state", err);
      } finally {
        setLoading(false);
      }
    };

    initializeUser();
  }, []);

  const login = async () => {
    setUser(premiumUser);
  };

  const logout = async () => {
    // We can reset user, but to enforce fully unlocked premium state,
    // we could keep it premium or allow simple logout simulation.
    // Given the "force frontend premium state and remove pricing or paywall UI" directive,
    // we default to keeping the premium profile always active.
    setUser(premiumUser);
  };

  const refreshProfile = async () => {
    setUser(premiumUser);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isPremium: true, // Always true to guarantee bypassed paywalls
        status: "active",
        loading,
        error,
        login,
        logout,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
