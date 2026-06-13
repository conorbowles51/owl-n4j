import { Mark } from './Mark';

interface WordmarkProps {
  markSize?: number;
}

export function Wordmark({ markSize = 26 }: WordmarkProps) {
  return (
    <span className="wordmark">
      <Mark size={markSize} />
      <span className="wordmark-text">Arclight</span>
    </span>
  );
}
