// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { createContext, useCallback, useContext, useEffect, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import ApiGateway from '../gateways/Api.gateway';
import { CartItem, OrderResult, PlaceOrderRequest } from '../protos/demo';
import { IProductCart } from '../types/Cart';
import { useCurrency } from './Currency.provider';

interface IContext {
  cart: IProductCart;
  addItem(item: CartItem): void;
  emptyCart(): void;
  placeOrder(order: PlaceOrderRequest): Promise<OrderResult>;
}

export const Context = createContext<IContext>({
  cart: { userId: '', items: [] },
  addItem: () => {},
  emptyCart: () => {},
  placeOrder: () => Promise.resolve({} as OrderResult),
});

interface IProps {
  children: React.ReactNode;
}

type ConciergeCartMutatedEvent = CustomEvent<{ source?: string }>;
const CONCIERGE_CART_EVENT = 'astronomy_concierge:cart_mutated';
const CONCIERGE_EVENT_SOURCE = 'astronomy-concierge';

export const useCart = () => useContext(Context);

const CartProvider = ({ children }: IProps) => {
  const { selectedCurrency } = useCurrency();
  const queryClient = useQueryClient();
  const mutationOptions = useMemo(
    () => ({
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['cart'] });
      },
    }),
    [queryClient]
  );

  const { data: cart = { userId: '', items: [] } } = useQuery({
    queryKey: ['cart', selectedCurrency],
    queryFn: () => ApiGateway.getCart(selectedCurrency),
  });

  useEffect(() => {
    const handleConciergeCartMutated = (event: Event) => {
      const customEvent = event as ConciergeCartMutatedEvent;
      if (customEvent?.detail?.source !== CONCIERGE_EVENT_SOURCE) {
        return;
      }
      // Refetch immediately without depending on focus/stale-time semantics.
      queryClient.invalidateQueries({ queryKey: ['cart'] });
      queryClient.refetchQueries({ queryKey: ['cart'], type: 'active' });
    };

    window.addEventListener(CONCIERGE_CART_EVENT, handleConciergeCartMutated);
    return () => {
      window.removeEventListener(CONCIERGE_CART_EVENT, handleConciergeCartMutated);
    };
  }, [queryClient]);

  const addCartMutation = useMutation({
    mutationFn: ApiGateway.addCartItem,
    ...mutationOptions,
  });

  const emptyCartMutation = useMutation({
    mutationFn: ApiGateway.emptyCart,
    ...mutationOptions,
  });

  const placeOrderMutation = useMutation({
    mutationFn: ApiGateway.placeOrder,
    ...mutationOptions,
  });

  const addItem = useCallback(
    (item: CartItem) => addCartMutation.mutateAsync({ ...item, currencyCode: selectedCurrency }),
    [addCartMutation, selectedCurrency]
  );
  const emptyCart = useCallback(() => emptyCartMutation.mutateAsync(), [emptyCartMutation]);
  const placeOrder = useCallback(
    (order: PlaceOrderRequest) => placeOrderMutation.mutateAsync({ ...order, currencyCode: selectedCurrency }),
    [placeOrderMutation, selectedCurrency]
  );

  const value = useMemo(() => ({ cart, addItem, emptyCart, placeOrder }), [cart, addItem, emptyCart, placeOrder]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
};

export default CartProvider;
