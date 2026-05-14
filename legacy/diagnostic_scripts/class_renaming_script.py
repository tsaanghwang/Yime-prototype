"""Legacy diagnostic: verify the retained class-base naming relationship."""


def test_class_renaming():
    from syllable.analysis.yinyuan import UncertainPitchYinyuan
    from syllable.analysis.zaoyin_yinyuan import NoiseYinyuan

    assert UncertainPitchYinyuan.__name__ == "UncertainPitchYinyuan"
    assert NoiseYinyuan.__bases__[0].__name__ == "UncertainPitchYinyuan"


def main() -> None:
    test_class_renaming()
    print("类名重构验证通过")


if __name__ == "__main__":
    main()
