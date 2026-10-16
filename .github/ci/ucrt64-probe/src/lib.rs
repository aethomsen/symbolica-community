#[cfg(test)]
mod tests {
    use rug::{Float, Integer, Rational};

    #[test]
    fn large_integer_and_rational_arithmetic() {
        let large: Integer = Integer::from(1) << 512;
        let mut result = large.clone();
        result += 1;
        result -= large;
        assert_eq!(result, 1);
        assert_eq!(Rational::from((1, 3)) + Rational::from((2, 3)), 1);
    }

    #[test]
    fn high_precision_mpfr_arithmetic() {
        let mut root = Float::with_val(256, 2);
        root.sqrt_mut();
        root.square_mut();
        root -= 2;
        root.abs_mut();
        assert!(root < Float::with_val(256, 1e-70));
    }
}
