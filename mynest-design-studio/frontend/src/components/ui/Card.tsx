import type { HTMLAttributes } from 'react';

export default function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  const classes = ['card', className].filter(Boolean).join(' ');
  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}
