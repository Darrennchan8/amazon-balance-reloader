from functools import wraps

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class AmazonBalanceReloaderException(Exception):
    def __init__(self, message, exception):
        self.message = message
        self.exception = exception

    def __str__(self):
        return f"AmazonBalanceReloaderException: {self.message}\n{self.exception}"


def throwable(message):
    def throwable(f):
        @wraps(f)
        def wrapper(*args, **kwds):
            try:
                return f(*args, **kwds)
            except Exception as inst:
                raise AmazonBalanceReloaderException(message, inst)

        return wrapper

    return throwable


class AmazonBalanceReloader:
    @throwable("Unable to connect to chromedriver!")
    def __init__(self, host, headless=True):
        chrome_options = webdriver.ChromeOptions()
        # @TODO(darrennchan8): Make sure that Compute Engine maps /dev/shm in docker container.
        #       Otherwise, we'll need to uncomment the following line.
        # chrome_options.add_argument('--disable-dev-shm-usage')
        if headless:
            chrome_options.add_argument("--headless")
        self.driver = webdriver.Remote(
            desired_capabilities=chrome_options.to_capabilities(),
            command_executor=f"http://{host}/wd/hub",
        )
        self.driver.implicitly_wait(5)
        self.authentication_exception = AmazonBalanceReloaderException(
            "authenticate() not called!", None
        )

    def __enter__(self):
        return self

    @throwable("Authentication failed!")
    def authenticate(self, username, password):
        try:
            self.driver.get("https://www.amazon.com/asv/reload/order")
            self.driver.find_element_by_xpath(
                "//button[contains(text(), 'Sign In')]"
            ).click()
            self.driver.find_element_by_xpath("//input[@type='email']").send_keys(
                username
            )
            self.driver.find_element_by_xpath("//*[@type='submit']").click()
            self.driver.find_element_by_xpath("//input[@type='password']").send_keys(
                password
            )
            self.driver.find_element_by_xpath("//*[@type='submit']").click()
            # Verify that authentication is successful and we are redirected back to the order page.
            self.driver.find_element_by_id("asv-manual-reload-amount")
            self.authentication_exception = None
        except Exception as inst:
            self.authentication_exception = AmazonBalanceReloaderException(
                "authenticate() was not successful!", inst
            )
            raise inst

    @throwable("Unable to reload card!")
    def reload(self, card_number, amount):
        if self.authentication_exception:
            raise self.authentication_exception
        self.driver.get("https://www.amazon.com/asv/reload/order")
        self.driver.find_element_by_id("asv-manual-reload-amount").send_keys(
            str(amount)
        )
        self.driver.find_element_by_xpath(
            f"//*[text()='ending in {card_number[-4:]}']"
        ).click()
        self.driver.find_element_by_xpath(f"//*[@id='form-submit-button']").click()
        try:
            self.driver.find_element_by_xpath(
                f"//*[contains(@class, 'pmts-selected')]//input[contains(@placeholder, '{card_number[-4:]}')]"
            ).send_keys(str(card_number))
            self.driver.find_element_by_xpath(
                "//*[contains(@class, 'pmts-selected')]//*[text()='Verify card']"
            ).click()
            WebDriverWait(self.driver, 30).until(
                EC.invisibility_of_element_located(
                    (
                        By.XPATH,
                        "//*[contains(@class, 'pmts-loading-async-widget-spinner-overlay')]",
                    )
                )
            )
            self.driver.find_element_by_xpath(f"//*[@id='form-submit-button']").click()
        except NoSuchElementException:
            pass
        # Verify that the reload was successful.
        self.driver.find_element_by_xpath(
            "//*[contains(text(), 'your reload order is placed')]"
        )

    def __exit__(self, type, value, tb):
        self.driver.quit()
