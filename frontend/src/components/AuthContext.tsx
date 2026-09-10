import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { api, setToken, getToken } from '../api';

interface AuthState {
  authenticated: boolean;
  username: string;
  fullName: string;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  authenticated: false,
  username: '',
  fullName: '',
  loading: true,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [loading, setLoading] = useState(true);

  // On mount, check if we have a valid token
  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    api.getMe()
      .then(user => {
        setUsername(user.username);
        setFullName(user.full_name);
        setAuthenticated(true);
      })
      .catch(() => {
        setToken(null);
        setAuthenticated(false);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = async (user: string, password: string) => {
    const res = await api.login(user, password);
    setToken(res.access_token);
    setUsername(res.username);
    setFullName(res.full_name);
    setAuthenticated(true);
  };

  const logout = () => {
    setToken(null);
    setAuthenticated(false);
    setUsername('');
    setFullName('');
  };

  return (
    <AuthContext.Provider value={{ authenticated, username, fullName, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
