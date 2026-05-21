export const apiUrl = (path: string) =>
  import.meta.env.DEV ? `http://localhost:8080${path}` : path;
