"""Legacy diagnostic: verify the retained NoiseYinyuan base-class relationship."""


def test_noise_yinyuan_base_class_relationship() -> None:
    from syllable.analysis.yinyuan import UncertainPitchYinyuan
    from syllable.analysis.zaoyin_yinyuan import NoiseYinyuan

    assert UncertainPitchYinyuan.__name__ == "UncertainPitchYinyuan"
    assert NoiseYinyuan.__bases__[0].__name__ == "UncertainPitchYinyuan"


def main() -> None:
    test_noise_yinyuan_base_class_relationship()
    print("类名重构验证通过")


if __name__ == "__main__":
    main()
