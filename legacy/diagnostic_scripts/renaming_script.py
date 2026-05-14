"""Legacy diagnostic: verify the retained Yinyuan renaming relationship."""


def test_renaming():
    from syllable.analysis.yinyuan import UncertainPitchYinyuan
    from syllable.analysis.zaoyin_yinyuan import NoiseYinyuan

    assert issubclass(NoiseYinyuan, UncertainPitchYinyuan)
    assert UncertainPitchYinyuan.__name__ == "UncertainPitchYinyuan"


def main() -> None:
    test_renaming()
    print("重命名关系验证通过")


if __name__ == "__main__":
    main()
