import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { RecoveryScreen } from '../src/screens/RecoveryScreen';
import { api } from '../src/auth/AuthProvider';

jest.mock('../src/auth/AuthProvider', () => ({ api: { requestRecovery: jest.fn(), verifyEmail: jest.fn(), resetPassword: jest.fn() } }));
jest.mock('expo-router', () => ({ router: { replace: jest.fn() } }));
jest.mock('../src/components/Screen', () => ({ Screen: ({ children }: React.PropsWithChildren) => <>{children}</> }));

beforeEach(() => { jest.clearAllMocks(); });
it('requests a code, validates confirmation and resets without creating a session', async () => {
  jest.mocked(api.requestRecovery).mockResolvedValue({ message: 'Check your email.' });
  jest.mocked(api.resetPassword).mockResolvedValue({ message: 'Password reset. Sign in again.' });
  const view = await render(<RecoveryScreen />);
  await fireEvent.changeText(view.getByLabelText('Recovery email'), 'USER@example.test');
  await fireEvent.press(view.getByText('Send email code'));
  await waitFor(() => expect(api.requestRecovery).toHaveBeenCalledWith('user@example.test', 'password'));
  await waitFor(() => expect(view.getByLabelText('Email code')).toBeTruthy());
  await fireEvent.changeText(view.getByLabelText('Email code'), '123456');
  await fireEvent.changeText(view.getByLabelText('New password'), 'Replacement-pass123');
  await fireEvent.changeText(view.getByLabelText('Confirm new password'), 'different');
  await fireEvent.press(view.getByText('Reset password'));
  expect(api.resetPassword).not.toHaveBeenCalled();
  await fireEvent.changeText(view.getByLabelText('Confirm new password'), 'Replacement-pass123');
  await fireEvent.press(view.getByText('Reset password'));
  await waitFor(() => expect(api.resetPassword).toHaveBeenCalledWith('user@example.test', '123456', 'Replacement-pass123'));
  await waitFor(() => expect(view.getByText('Password reset. Sign in again.')).toBeTruthy());
});

it('verifies email and shows server errors without reporting success', async () => {
  jest.mocked(api.requestRecovery).mockResolvedValue({ message: 'Check email.' });
  jest.mocked(api.verifyEmail).mockRejectedValue(new Error('The code has expired.'));
  const view = await render(<RecoveryScreen />);
  await fireEvent.press(view.getByText('Switch to email verification'));
  await fireEvent.changeText(view.getByLabelText('Recovery email'), 'user@example.test');
  await fireEvent.press(view.getByText('Send email code'));
  await waitFor(() => expect(view.getByLabelText('Email code')).toBeTruthy());
  await fireEvent.changeText(view.getByLabelText('Email code'), '123456');
  await fireEvent.press(view.getByText('Verify email'));
  await waitFor(() => expect(view.getByText('The code has expired.')).toBeTruthy());
  expect(view.queryByText('Email verified.')).toBeNull();
});
